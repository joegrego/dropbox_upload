# dropbox_upload
Tool for uploading large files to dropbox with an option to zip-and-share-a-download-link.

This tool was originally developed for the University of Michigan Advanced Genomics Core. I put it here to share with other developers who are trying to use the Python Dropbox API.

# Setup 
```
python3 -v venv venv
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
