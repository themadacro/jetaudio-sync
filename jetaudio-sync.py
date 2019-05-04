#
# JetAudio Music Syncer
# Copyright 2019 The Mad Acro -- Licensed under GPLv2 only.
#
# Here's the plan....
#
# I have always used JetAudio on Android.  You copy a huge directory tree of media files,
# carefully curated with directories and filenames, etc, on to an SD card and then pop it
# into your Android device, and JetAudio will let you play your media files off of that
# filesystem.  It's exactly the way Rockbox works, for those of you who used that.
#
# JetAudio exists on ios, but none of the built in ios tools support arbitrary directory
# trees, at least nothing close to using cp -R onto an sd card!
#
# But JetAudio exposes an internal API ("wifi sharing"), and an internal website that uses
# that API.  But the website is clunky and doesn't let you transfer entire trees of stuff.
# That's where this script comes in.
#
# You give this script the root of a directory tree containing a hierarchy of media files,
# and you tell it what to name that root in JetAudio, and it copies everything over for you,
# carefully retaining the directory structure.
#
import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder
import os.path
import json
from os import walk
from os import listdir
from os.path import isfile, join
import glob
import sys
import urllib

api_server = ""
create_endpoint = ""
list_endpoint = ""
upload_endpoint = ""
delete_endpoint = ""
remote_root = "/"
local_root = "."

def init_server(ipaddr):
    global api_server
    global create_endpoint
    global list_endpoint
    global upload_endpoint
    global delete_endpoint
    api_server = "http://%s" % (ipaddr,)
    create_endpoint = "%s/create" % (api_server,)
    list_endpoint = "%s/list" % (api_server,)
    upload_endpoint = "%s/upload" % (api_server,)
    delete_endpoint = "%s/delete" % (api_server,)

#
# create_remote_directory - create a specific directory. 
#  INTERNAL FUNCTION -- 
#  You must have checked that the directory doesn't exist first.
#  Only check_for_remote_directory() does that...
#
def create_remote_directory(destination_place):
    #print("Creating directory %s" % (destination_place,))
    r = requests.post(create_endpoint, data={"path": destination_place})
    print("Create directory complete: %d / %s" % (r.status_code, r.content,))

#
# check_for_remote_directory - ensure a directory exists prior to using it
#   INTERNAL FUNCTION --
#   This function is similar to 'mkdir' -- that means it fails if parent dirs don't eixst.
#   You must have checked that all the PARENT directories to this one exist first.
#   Only check_for_remote_directory_recursively() does that...
#
def check_for_remote_directory(destination_place):
    #print("checking for existance of %s" % (destination_place,))
    r = requests.get(list_endpoint + "?path=%s" % (urllib.parse.quote(destination_place),))
    #print("check complete: %d / %s" % (r.status_code, r.content,))
    if r.status_code == 404:
        create_remote_directory(destination_place)

#
# check_for_remote_directory_recursively - ensure a directory exists prior to using it.
#    PUBLIC FUNCTION --
#    This function is similar to 'mkdir -p' -- it will create a directory and any 
#    necessary parent subdirectories, so in the end 'destination_place' exists.
#
def check_for_remote_directory_recursively(destination_place):
    accumulator = ""
    x = destination_place.split("/")
    for portion in x:
       accumulator = "%s/%s" % (accumulator, portion)
       check_for_remote_directory(accumulator)

# 
# upload_one_file - upload one local file to a remote directory root
#    INTERNAL FUNCTION --
#    Now "path" may be in a subdirectory, like "dir1/dir2/file.mp3"
#    And "root" should be the same for all files you're uploading (like "/myfiles")
#    This will copy "dir1/dir2/file.mp3" local to "/myfiles/dir1/dir2/file.mp3" remote
#    This function auto-creates any remote directories needed to hold the file.
#
def upload_one_file(path, root):
    path_dirname = os.path.dirname(path);
    #print("path_dirname is %s" % (path_dirname,))
    path_basename = os.path.basename(path);
    #print("path_basename is %s" % (path_basename,))
    destination_place = "%s/%s" % (root, path_dirname)
    #print("destination_place is %s" % (destination_place,))

    check_for_remote_directory_recursively(destination_place)

    try:
        m = MultipartEncoder(
            fields={'path': destination_place, 'files[]': (path_basename, open(path, "rb"), 'audio/mp3')}
        )
    except UnicodeEncodeError:
       print("Can't upload %s/%s - bummer" % (destination_place,path_basename))
       return

    print("Uploading %s -> %s/%s" % (path, destination_place, path_basename))
    r = requests.post(upload_endpoint, data=m, headers={'Content-Type': m.content_type})
    if r.status_code >= 300:
        print("Upload complete with error: %d / %s" % (r.status_code, r.content,))

def remove_remote_empty_directory(path):
   r = requests.post(delete_endpoint, data={"path": path})
   if r.status_code > 300:
        print("Failed to remove empty directory %s: %d %s" % (path, r.status_code, r.content))
   else:
        print("Removed empty directory %s" % (path,))

def remove_remote_file(path):
   #print("Here i would delete the remote file %s" % (path,))
   r = requests.post(delete_endpoint, data={"path": path})
   if r.status_code > 300:
        print("Failed to remove remote file %s: %d %s" % (path, r.status_code, r.content))
   else:
        print("Removed remote file %s" % (path,))

#
# get_files_in_directory - collect all files in a remote directory
#    INTERNAL FUNCTION --
#    Given one single directory, it returns the file items in that directory
#    Some of them may be files, some may be directories.
#
def get_files_in_directory(directory):
    r = requests.get(list_endpoint + "?path=%s" % (urllib.parse.quote(directory),))
    if r.status_code >= 300:
        print("dirlist complete: %d / %s" % (r.status_code, r.content,))
        print("Response status code: %d" % (r.status_code,))
        print("Response json %s" % (json.dumps(r.json()),))
    return r.json()

#
# traverse_directory_tree - collect all files in a remote directory tree
#    INTERNAL FUNCTION -- 
#    Given a directory tree root, return all files relative to that root.
#    Essentially, this enumerates all files under a directory tree.
#    This would be needed if you wanted to compare a "local" and "remote" list
#    to see which files need to be pushed.
#
def traverse_directory_tree(directory):
    results = []

    dirlist = get_files_in_directory(directory)
    for file in dirlist:
        #print("processing %s" % (file["path"],))
        if file["path"].endswith("/"):
            #print("%s is a directory -- we must go deeper" % (file["path"],))
            subdirents = traverse_directory_tree(file["path"])
            for i in subdirents:
                #print("Appending subdirent %s to my list" % (i["path"],))
                results.append(i)
        else:
            #print("I spy with my little eye, a file %s" % (file["path"],))
            results.append(file)

    return results

#
# summarize_remote - collect all files on the remote
#    INTERNAL FUNCTION
#    Returns all files on the remote as a hash, 
#       retval[remote_filename] = remote_filesize
#    where "remote_filename" is the full path on the remote.
#
def summarize_remote():
    all_files = {}
    files = traverse_directory_tree("/")
    for file in files:
        all_files[file["path"]] = file["size"]
    return all_files

def summarize_remote_tree():
    retval = {}
    compound_root = "%s/%s" % (remote_root, local_root)

    all_files = summarize_remote()
    for file in all_files:
        if file.startswith(compound_root):
            retval[file] = all_files[file]
    return retval

def find_empty_directories(directory):
    results = []

    dirlist = get_files_in_directory(directory)
    if len(dirlist) == 0:
        #print("%s is an empty directory" % (directory,))
        results.append(directory)
    else:
        for file in dirlist:
            #print("processing %s" % (file["path"],))
            if file["path"].endswith("/"):
                subdirents = find_empty_directories(file["path"])
                for i in subdirents:
                    #print("Appending subdirent %s to my list" % (i,))
                    results.append(i)

    return results

def summarize_empty_directories():
    results = find_empty_directories("/")
    #for dirname in results:
    #    print("empty directory -> %s" % (dirname,))
    return results

# File types we want to upload:
#   aif
#   avi
#   flac
#   flv
#   m4a
#   mp3
#   ogg
#   opus
#   wav
#
# (I am not uploading flac or wav, for my own personal reasons. 
#  you may want to add those!)
#
exts = ("aif", "avi", "m4a", "mp3", "ogg", "opus")
#exts = ("aif", "avi", "flac", "m4a", "mp3", "ogg", "opus", "wav")

def summarize_local(root):
    print("root is %s" % (root,))
    result = []
    for file in glob.iglob(root + "/**/*.*", recursive=True):
        for ext in exts:
            if file.lower().endswith(ext):
                result.append(file)
    return result


def sync_local_to_remote(remote_files, local_files):
   for local_file in local_files:
      remote_file = "%s/%s" % (remote_root, local_file)
      # XXX TODO - Check file sizes - TODO XXX
      #  remote_files[remote_file] is the file size.
      if remote_file in remote_files:
         print("OK  %s" % (remote_file,))
         remote_files[remote_file] = -1
      else:
         upload_one_file(local_file, remote_root)


##-------------------------------------------
def operation_sync():
   remote_files = summarize_remote_tree()
   local_files = summarize_local(local_root)

   sync_local_to_remote(remote_files, local_files)

   for remote_file in remote_files:
      if remote_files[remote_file] != -1:
          remove_remote_file(remote_file)

def operation_merge():
   remote_files = summarize_remote_tree()
   local_files = summarize_local(local_root)

   sync_local_to_remote(remote_files, local_files)

def operation_remove():
   remote_files = summarize_remote()
   for file in remote_files:
       if file.startswith(remote_root):
           remove_remote_file(file)

def operation_prune():
   empty_directories = summarize_empty_directories()
   for empty_dir in empty_directories:
       if empty_dir.startswith(remote_root):
           remove_remote_empty_directory(empty_dir)

def usage(progname):
   print("Usage: %s operation ip-address target [source]" % (sys.argv[0]))
   print("Usage Examples:")
   print("  %s sync 192.168.1.155 / mymedia/subdir")
   print("  %s merge 192.168.1.155 / mymedia/subdir")
   print("  %s remove 192.168.1.155 /mymedia")
   print("  %s prune 192.168.1.155 /")
   print("")
   print("Operations")
   print(" sync")
   print("        Ensure the remote device is the same as local.")
   print("        Files on remote that are not present locally will be removed.")
   print("        sync won't remove directories (see prune for how to do that)")
   print(" merge")
   print("        Merges the local directory to the remote device")
   print("        No files on the remote device will be removed")
   print(" remove")
   print("        Remove a directory and everything underneath it.")
   print("        This is great if you want to start over.")
   print(" prune")
   print("        Find and delete any empty directories under root")
   print("        This will not remove any files, only empty directories.")
   sys.exit(0)

##---------------------------------------------
if len(sys.argv) < 4:
    usage()

operation = sys.argv[1]
init_server(sys.argv[2])
remote_root = sys.argv[3]
if len(sys.argv) >= 5:
    local_root = sys.argv[4]

if operation == "sync" or operation == "update":
    if len(sys.argv) != 5:
        usage()
    operation_sync()
elif operation == "cp" or operation == "copy" or operation == "merge":
    if len(sys.argv) != 5:
        usage()
    operation_merge()
elif operation == "rmdir" or operation == "wipe":
    if len(sys.argv) != 4:
        usage()
    operation_remove()
elif operation == "prune":
    if len(sys.argv) != 4:
        usage()
    operation_prune()
else:
    usage()


