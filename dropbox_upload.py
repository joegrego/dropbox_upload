#!/usr/bin/env python3
"""
Upload a file to Dropbox using the API.

Usage for "zipping and uploading":
 python3 dropbox_upload.py -z -l info -s /path/to/mydir -d "/CompanyDropboxShare/zips/18-AK.zip" -o mydir_output.json -ar
(you would then use the mydir_output.json file that gets created to craft an email message to interested parties...)


Thanks to FrustratedUser3 at https://www.dropboxforum.com/t5/Dropbox-API-Support-Feedback/Oauth2-refresh-token-question-what-happens-when-the-refresh/td-p/486241

you may need to:
pip install dropbox
pip install humanize
"""

# Copyright (c) 2024 by the Regents of the University of Michigan, All Rights Reserved
# Michigan Advanced Genomics Core

import argparse
import configparser
import json
import logging
import os
import secrets
import string
import sys
import time
import zipfile
from datetime import timedelta, datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import dropbox
import humanize
from dropbox import DropboxOAuth2FlowNoRedirect, common

# you'll want to create a new dropbox app key for each new dropbox app you write
APP_KEY = os.environ["MY_DROPBOX_API_KEY"]
TIMEOUT = 900
CHUNK_SIZE = 4 * 1024 * 1024
# and probably you should use the name of your program, not mine, for the configuration file.
my_config_file = os.path.join(os.path.expanduser("~"), ".dropbox.cfg")
refresh_token = None
logger = logging.getLogger(__name__)


def set_logging_level(logging_level, logger):
    level = logging.WARNING
    if logging_level == 'error':
        level = logging.ERROR
    elif logging_level == 'warning':
        level = logging.WARNING
    elif logging_level == 'info':
        level = logging.INFO
    elif logging_level == 'debug':
        level = logging.DEBUG

    logging.basicConfig(format='%(asctime)s %(name)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    logger.setLevel(level=level)


def add_logging_arg(parser):
    parser.add_argument('--logging_level', '-l', type=str, help="error, warning, info, debug", default='warning',
                        choices={'error', 'warning', 'info', 'debug'})


def get_refresh_token(interactive):
    """
    Use refresh tokens, stored in a config file, so you only have to use the login page cut/paste nonsense one time.
    :param interactive: True/False to run this function interactively or fail if can't find token
    :return:
    """
    config = configparser.ConfigParser()

    if not os.path.isfile(my_config_file):
        if not interactive:
            logger.critical(f"Failed to find dropbox config file in home directory, try running this to generate file:\n"
                            f"python3 {__file__} -a -l debug\n")
            raise RuntimeError(f"There is no config file at {my_config_file} and we are not interactive")
        tokens = make_user_login_to_get_tokens()
        config[APP_KEY] = {}
        config[APP_KEY]['access_token'] = tokens.access_token
        config[APP_KEY]['refresh_token'] = tokens.refresh_token
        config[APP_KEY]['account_id'] = tokens.account_id
        config[APP_KEY]['scope'] = str(tokens.scope)
        config[APP_KEY]['expiration'] = str(tokens.expires_at)
        with open(my_config_file, 'w') as configfile:
            config.write(configfile)
        logger.info(f"Configuration saved to {my_config_file}")
    else:
        config.read(my_config_file)
        logger.debug(f"Loaded configuration from {my_config_file}")

    return config[APP_KEY]['refresh_token']


def make_user_login_to_get_tokens():
    """
    This is the login page cut and paste nonsense. Only called when absolutely needed.

    :return: oauth_result from our friends at dropbox
    """
    auth_flow = DropboxOAuth2FlowNoRedirect(APP_KEY, use_pkce=True, token_access_type='offline')
    authorize_url = auth_flow.start()

    print(f"Login Here:\n{authorize_url}")

    auth_code = input("Paste Access Code: ").strip()

    try:
        logger.debug("Getting oauth tokens...")
        oauth_result = auth_flow.finish(auth_code)
        logger.debug("done.")
    except RuntimeError as ex:
        logger.error(f"error calling DropboxOAuth2FlowNoRedirect.finish({auth_code})")
        logger.error(ex)
        logger.error("Maybe you pasted the wrong thing from the web site?")
        sys.exit(42)

    return oauth_result

def download_file(dbx, dropbox_path, local_path):
    """Download a file from Dropbox to a local directory."""
    with open(local_path, "wb") as f:
        metadata, res = dbx.files_download(dropbox_path)
        f.write(res.content)


def download_folder(dbx, folder_path, local_dir):
    """Download an entire folder from Dropbox to a local directory."""
    total_files = 0
    total_folders = 0

    try:
        os.makedirs(local_dir, exist_ok=True)
        response = dbx.files_list_folder(folder_path)

        while True:
            for entry in response.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    local_file_path = os.path.join(local_dir, entry.name)
                    logger.info(f"Downloading file {local_file_path}")
                    download_file(dbx, entry.path_lower, local_file_path)
                    total_files += 1
                elif isinstance(entry, dropbox.files.FolderMetadata):
                    new_local_dir = os.path.join(local_dir, entry.name)
                    logger.info(f"Creating folder {new_local_dir}")
                    sub_files, sub_folders = download_folder(dbx, entry.path_lower, new_local_dir)
                    total_folders += 1 + sub_folders
                    total_files += sub_files

            if not response.has_more:
                break
            response = dbx.files_list_folder_continue(response.cursor)

    except dropbox.exceptions.ApiError as err:
        logger.critical(f"API error: {err}")
        raise

    return total_files, total_folders


def big_download_directory(dropbox_path, local_dir, interactive=False, use_team_root=True):
    global refresh_token
    if not refresh_token:
        logger.debug("getting refresh token")
        refresh_token = get_refresh_token(interactive)
    else:
        logger.debug("reusing refresh token")

    with dropbox.Dropbox(oauth2_refresh_token=refresh_token, app_key=APP_KEY) as dbx:
        try:
            if use_team_root:
                root_namespace_id = dbx.users_get_current_account().root_info.root_namespace_id
                dbx = dbx.with_path_root(dropbox.common.PathRoot('root', value=root_namespace_id))
                logger.debug(f"Using team namespace id {root_namespace_id}")
            else:
                logger.debug("Using 'user' namespace (WARNING! this may not be what you wanted!)")

            total_files, total_folders = download_folder(dbx, dropbox_path, local_dir)

        except Exception as ex:
            logger.critical(f"ERROR: Dropbox upload Failed with error:\n{ex}")
            raise

        logger.info(f"Downloaded {total_files} files and {total_folders} folders")
        return total_files, total_folders


def upload(file_path, target_path, dbx, autorename=False):
    with open(file_path, "rb") as f:
        file_size = os.path.getsize(file_path)
        if file_size <= CHUNK_SIZE:
            logger.debug("sending all data at once")
            upload_return = dbx.files_upload(f.read(), target_path, autorename=autorename, mode=dropbox.files.WriteMode.add)
            logger.debug(upload_return)
            actual_path = upload_return.path_display
        else:
            logger.debug("starting file upload")
            upload_session_start_result = dbx.files_upload_session_start(f.read(CHUNK_SIZE))
            cursor = dropbox.files.UploadSessionCursor(session_id=upload_session_start_result.session_id, offset=f.tell())
            commit = dropbox.files.CommitInfo(path=target_path, mode=dropbox.files.WriteMode.add, autorename=autorename)
            while f.tell() < file_size:
                if (file_size - f.tell()) <= CHUNK_SIZE:
                    logger.debug('finishing file upload')
                    upload_return = dbx.files_upload_session_finish(f.read(CHUNK_SIZE), cursor, commit)
                    logger.debug(upload_return)
                    actual_path = upload_return.path_display
                else:
                    logger.debug(f"Uploading chunk {f.tell()} of {file_size} {round(f.tell() / file_size * 100, 2)}%")
                    dbx.files_upload_session_append(f.read(CHUNK_SIZE), cursor.session_id, cursor.offset)
                    cursor.offset = f.tell()
    logger.info(f"Actual uploaded path is {actual_path}")
    return actual_path


def big_file_upload(source, destination, interactive=True, use_team_root=True, password=None, expiration=None, autorename=False):
    global refresh_token
    if not refresh_token:
        logger.debug("getting refresh token")
        refresh_token = get_refresh_token(interactive)
    else:
        logger.debug("reusing refresh token")

    return_struct = {
        "url": None,
        "dropbox_path": None
    }
    # use the 'with' statement, so we don't need to close the connection to dropbox manually
    with dropbox.Dropbox(oauth2_refresh_token=refresh_token, app_key=APP_KEY) as dbx:
        try:
            if use_team_root:
                # See https://developers.dropbox.com/dbx-team-files-guide and https://www.dropboxforum.com/t5/Dropbox-API-Support-Feedback/Folders-that-are-visible-from-the-SDK-don-t-appear-to-be-visible/td-p/738326
                # Starting in June 2024 at UMich, we now have to tell the API that we want to use the "team root" instead of the "user root"
                # for uploads. If you don't do this, files you upload will go under the folder "All files/<full name>/" instead of
                # what we want for the AGC, which is to use the "university of michigan" folder as the root.
                root_namespace_id = dbx.users_get_current_account().root_info.root_namespace_id
                dbx = dbx.with_path_root(dropbox.common.PathRoot('root', value=root_namespace_id))
                logger.debug(f"Using team namespace id {root_namespace_id}")
            else:
                logger.debug(f"Using 'user' namespace (WARNING! this may not be what you wanted!)")

            uploaded_path = upload(file_path=source, target_path=destination, dbx=dbx, autorename=autorename)
            return_struct["dropbox_path"] = uploaded_path

            if password:
                # https://dropbox-sdk-python.readthedocs.io/en/latest/api/sharing.html#dropbox.sharing.SharedLinkSettings
                shared_link_settings = dropbox.sharing.SharedLinkSettings(
                    require_password=True,
                    link_password=password,
                    allow_download=True,
                    expires=expiration,
                    audience=dropbox.sharing.LinkAudience.public)
                logger.debug(f"Shared link settings: {shared_link_settings}")

                # from datetime import datetime
                logger.info("sleeping a few seconds to make sure the file finishes upload")
                time.sleep(10)

                shared_link_metadata = dbx.sharing_create_shared_link_with_settings(path=uploaded_path, settings=shared_link_settings)
                logger.debug(f"Shared link metadata: {shared_link_metadata}")
                logger.info(shared_link_metadata.url)

                return_struct["url"] = shared_link_metadata.url

        except Exception as ex:
            logger.critical(f"ERROR: Dropbox upload Failed with error:\n{ex}")
            raise
    logger.debug("Upload Complete!")
    return return_struct


def zip_folder(folder_path, output_path):
    """
    Zip the folder_path into a file in the output_path.
    """
    with zipfile.ZipFile(output_path, 'x', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, folder_path)  # Preserve folder structure
                logger.debug(f"Zipping {os.path.basename(relative_path)}")
                zipf.write(file_path, relative_path)


def generate_password():
    """
    Create an insecure password.

    See https://docs.python.org/3/library/secrets.html#recipes-and-best-practices for more info
    """
    alphabet = string.hexdigits
    password = ''.join(secrets.choice(alphabet).lower() for i in range(12))  # for a 12-character password
    return password


def convert_dropbox_url_into_download_only(the_url):
    """
    force the user to "download" instead of "open" a file on Dropbox file by changing the query parameter "dl" from 0 to 1.

    'https://www.dropbox.com/scl/fi/0l2yq2bjqvnzlzwfqh3h4/18-AK.zip?rlkey=97yz7amqzzoxz5q86vs1e2m7g&dl=0' opens the target zip file, but
    'https://www.dropbox.com/scl/fi/0l2yq2bjqvnzlzwfqh3h4/18-AK.zip?rlkey=97yz7amqzzoxz5q86vs1e2m7g&dl=1' makes the user download that zip file!

    See https://help.dropbox.com/share/force-download
    """
    parsed_url = urlparse(the_url)
    query_params = parse_qs(parsed_url.query)
    if query_params.get('dl') == ['0']:
        query_params['dl'] = ['1']
    # Reconstruct the URL with the new query parameter  (thanks, umgpt!)
    new_query_string = urlencode(query_params, doseq=True)
    updated_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, new_query_string, parsed_url.fragment))
    return (updated_url)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Send exactly one file to Dropbox.")
    parser.add_argument("-s", "--source", default="", required=False,
                        help="Source file to copy from on computer"),
    parser.add_argument("-d", "--destination", default="", required=False,
                        help="Destination folder path in DropBox")
    parser.add_argument("-a", "--authenticate", action="store_true", help="Only authenticate without transferring")
    parser.add_argument("-ar", "--auto_rename", action="store_true", help="If there is a conflict in the target filename, "
                                                                          "have the dropbox API auto-rename the file in dropbox.")
    parser.add_argument("-z", "--zip", action="store_true", help="Create a zip file of the source and upload that zip")
    parser.add_argument("-p", "--password", default=None, help="Put a password on the zip file; defaults to creating its own password")
    parser.add_argument("-ed", "--expiration_days", type=int, default=14, help="How many days until the zip/download link expires. Default is 14.")
    parser.add_argument("-zfp", "--zip_file_path", required=False, help="if -z, use this as the full zip file path "
                                                                        "(including the name of the zip file itself) "
                                                                        "like /tmp/123456-AB.zip. If absent, defaults to ./<source>.zip")
    parser.add_argument("-o", "--output", default="", required=False, help="Where to write a JSON of the Dropbox URL and password "
                                                                           "that get generated during a -z run")
    parser.add_argument("--root", choices=['team', 'user'], default='team', help="Default is to use the team (U of M) root; to use your user root, specify 'user'")
    add_logging_arg(parser)
    args = parser.parse_args()
    set_logging_level(args.logging_level, logger)

    if args.authenticate:
        get_refresh_token(interactive=True)
        sys.exit(0)

    if not args.source:
        raise ValueError("Must specify source")
    elif not os.path.exists(args.source):
        raise ValueError(f"Source file/folder {args.source} does not exist")
    if not args.destination:
        raise ValueError("Must specify destination")

    if args.root == 'team':
        use_team_root = True
    else:
        use_team_root = False

    dropbox_input_path = args.source
    password = args.password
    expiration_date = None

    if args.zip:
        if args.zip_file_path:
            output_path = os.path.abspath(args.zip_file_path)
        else:
            zip_filename = Path(dropbox_input_path).stem
            if not zip_filename:
                zip_filename = os.path.basename(os.path.abspath(os.path.curdir))
            output_path = os.path.abspath(f"./{zip_filename}.zip")

        if os.path.exists(output_path):
            raise FileExistsError(f"The output zip {output_path} already exists. If you want to re-run this,\nrm -v {output_path}")
        if not os.path.exists(dropbox_input_path):
            raise FileNotFoundError(f'"{dropbox_input_path}" does not exist')
        logger.info(f"Zipping {dropbox_input_path} to {output_path}")

        zip_folder(dropbox_input_path, output_path)
        logger.info(f"{output_path} is {humanize.naturalsize(os.path.getsize(output_path))}")

        # use the ZIP file as the source for dropbox; we're only uploading one file!
        dropbox_input_path = output_path

        if not password:
            password = generate_password()
        logger.info(f"The password is: {password}")

        expiration_date = datetime.today() + timedelta(days=args.expiration_days)
        logger.info(f"Expiration date is {humanize.naturaldate(expiration_date)}")

    try:
        upload_return = big_file_upload(dropbox_input_path, args.destination, use_team_root=use_team_root,
                                        password=password, expiration=expiration_date,
                                        autorename=args.auto_rename)
    except Exception as e:
        logger.error(e)
        sys.exit(42)

    if args.zip:
        download_only_url = convert_dropbox_url_into_download_only(upload_return["url"])
        output_json = {
            "url": download_only_url,
            "password": password,
            "expiration_date": expiration_date.isoformat(timespec='seconds'),
            "size": os.path.getsize(dropbox_input_path),
            "source": os.path.abspath(args.source),
            "dropbox_path": upload_return["dropbox_path"]
        }
        if args.output:
            with open(args.output, "w") as f:
                f.write(json.dumps(output_json, indent=4))
        logger.info(json.dumps(output_json, indent=4))
