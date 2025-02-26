# dropbox_upload
Tool for uploading large files to dropbox with an option to zip-and-share-a-download-link.

This tool was originally developed for the University of Michigan Advanced Genomics Core. I put it here to share with other developers who are trying to use the Python Dropbox API.

# Setup 
```
python3 -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt
export MY_DROPBOX_API_KEY=NonyaBizzness
```

# To zip a directory, upload it, and get a public download-only link to that zip (in dropbox) that expires in 2 weeks
```
python3 dropbox_upload.py -z -l info -s /path/to/mydir -d "/CompanyDropboxShare/zips/mystuff.zip" -o mystuff_output.json -ar
```

# To upload a very large file (currently dropbox maxes out at 350GB per file, as described in their API docs) to your "user" dropbox space
```
python3 dropbox_upload.py -s /path/to/mybigfile.big -d "/bigfiles/mybigfile.big" --root user
```

# Dropbox is weird about duplicate file contents
Dropbox will, in essence, ignore an upload of a file with the same name and the same contents. That means that although you specify `-ar`, you may not get a "new" file (like with parenthesis and a number). That's a Dropbox thing, and if you don't like it, call them.

When testing with the same file over and over again, you probably want to delete the "target" file in dropbox each time. 

# Faking a "Dropbox Transfer"
Dropbox's API doesn't have a way to do a "Dropbox Transfer" (although they do have a way to do a Share, which is NOT the same).  To do a fake dbox transfer, you can do something like this:

```
    current_time_string = datetime.now().strftime("%Y%m%d%H%M%S")
    delivery_file_name_with_time = f"{the_file_name}__dropbox_{current_time_string}"

    #
    # Pull the files down from Dropbox
    #
    dropbox_pull_source = f"/{the_dropbox_path}/{the_folder}"
    dropbox_pull_target = os.path.join(temporary_dir_path, f"{delivery_file_name_with_time}")
    logger.info(f"Downloading {dropbox_pull_source} to {dropbox_pull_target}")

    total_files, total_folders = dropbox_upload.big_download_directory(dropbox_pull_source, dropbox_pull_target)
    logger.info(f"Total files downloaded: {total_files}")

    #
    # create a zip of the downloaded directory and upload it to dropbox
    #

    dropbox_destination = f"/{the_dropbox_path}/delivery_zips/{delivery_file_name_with_time}.zip"

    zip_file_path = os.path.join(temporary_dir_path, f"{delivery_file_name_with_time}.zip")
    text_file_path = os.path.join(temporary_dir_path, f"{delivery_file_name_with_time}.txt")
    logger.info(f"Creating {zip_file_path} and uploading to {dropbox_destination}")

    dropbox_upload_json = dropbox_upload.do_upload(
        auto_rename=True,
        destination=dropbox_destination,
        dropbox_input_path=dropbox_pull_target,
        expiration_days=30,
        is_zip=True,
        password=None,
        source=dropbox_pull_target,
        use_team_root=True,
        zip_file_path=zip_file_path
    )

    logger.info(f"Uploaded {dropbox_upload_json.get('source')} ({humanize.naturalsize(dropbox_upload_json.get('size'))}) to {dropbox_destination}")
    logger.debug(json.dumps(dropbox_upload_json, indent=4))

    #
    # Create text file with instructions
    #

    text_lines = []
    text_lines.append(f"DROPBOX TRANSFER FOR {the_folder}\n\n")
    text_lines.append(f"A PC-usable subset of the data for project {sr_name} is available on Dropbox at the link: {dropbox_upload_json['url']}\n\n")
    text_lines.append(f"The link password is: {dropbox_upload_json['password']}\n\n")
    text_lines.append(f"The size of this zip file is approximately {humanize.naturalsize(dropbox_upload_json['size'])}\n\n")
    text_lines.append(f"The Dropbox link will expire on: {datetime.fromisoformat(dropbox_upload_json['expiration_date']).date()}\n\n")

    logger.info(" ".join(text_lines))

    with open(text_file_path, "wt") as text_file:
        text_file.writelines(text_lines)

    logger.info(f"Created {text_file_path}")
```
