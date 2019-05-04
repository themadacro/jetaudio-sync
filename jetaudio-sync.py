#!/usr/bin/env python3
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
import glob
from os.path import basename, dirname
import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder
import sys
import urllib

##------------------------------------------
api_server = ""
create_endpoint = ""
list_endpoint = ""
upload_endpoint = ""
delete_endpoint = ""


def init_remote_routes(ipaddr):
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


##------------------------------------------
#
# create_remote_directory - create a specific directory.
#  INTERNAL FUNCTION --
#  You must have checked that the directory doesn't exist first.
#  Only check_for_remote_directory() does that...
#
def create_remote_directory(destination_place):
    if __debug__:
        print("Creating directory %s" % (destination_place,))
    r = requests.post(create_endpoint, data={"path": destination_place})
    print("Successfully created directory %s (%d / %s)" % (destination_place,
                                                           r.status_code, r.content))


#
# check_for_remote_directory - ensure a directory exists prior to using it
#   INTERNAL FUNCTION --
#   This function is similar to 'mkdir' -- that means it fails if parent dirs don't eixst.
#   You must have checked that all the PARENT directories to this one exist first.
#   Only check_for_remote_directory_recursively() does that...
#
def check_for_remote_directory(destination_place):
    if __debug__:
        print("checking for existance of %s" % (destination_place,))
    r = requests.get(list_endpoint + "?path=%s" % (urllib.parse.quote(destination_place),))
    if __debug__:
        print("check complete: %d / %s" % (r.status_code, r.content,))
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
    path_dirname = dirname(path)
    #print("path_dirname is %s" % (path_dirname,))
    path_basename = basename(path)
    if __debug__:
        print("path_basename is %s" % (path_basename,))
    destination_place = "%s/%s" % (root, path_dirname)
    if __debug__:
        print("destination_place is %s" % (destination_place,))

    check_for_remote_directory_recursively(destination_place)

    try:
        m = MultipartEncoder(
            fields={'path': destination_place, 'files[]': (path_basename,
                                                           open(path, "rb"), 'audio/mp3')}
        )
    except UnicodeEncodeError:
        print("Can't upload %s/%s - bummer" % (destination_place, path_basename))
        return

    r = requests.post(upload_endpoint, data=m, headers={'Content-Type': m.content_type})
    if r.status_code >= 300:
        print("FAILED upload %s -> %s/%s (%d / %s)" % (path, destination_place, path_basename,
                                                       r.status_code, r.content,))
    else:
        print("Successfully uploaded %s -> %s/%s" % (path, destination_place, path_basename))


def remove_remote_empty_directory(path):
    r = requests.post(delete_endpoint, data={"path": path})
    if r.status_code > 300:
        print("Failed to remove empty directory %s: %d %s" % (path, r.status_code, r.content))
    else:
        print("Removed empty directory %s" % (path,))


def remove_remote_file(path):
    if __debug__:
        print("Here i would delete the remote file %s" % (path,))
    r = requests.post(delete_endpoint, data={"path": path})
    if r.status_code > 300:
        print("Failed to remove remote file %s: %d %s" % (path, r.status_code, r.content))
    else:
        print("Removed remote file %s" % (path,))


##---------------------------------------------
#
# get_files_in_directory - collect all files in a remote directory
#    INTERNAL FUNCTION --
#    Given one single directory, it returns the file items in that directory
#    Some of them may be files, some may be directories.
#
def get_files_in_directory(directory):
    url = list_endpoint + "?path=%s" % (urllib.parse.quote(directory),)
    if __debug__:
        print("get_files_in_directory: %s" % (url,))
    r = requests.get(url)

    if r.status_code >= 300:
        print("ERROR: dirlist complete: %d / %s" % (r.status_code, r.content,))
        print("ERROR: Response status code: %d" % (r.status_code,))
        print("ERROR: Response json %s" % (r.text,))
        return None
    else:
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
    if __debug__:
        print("traverse_directory_tree: %s" % (directory,))
    results = []

    dirlist = get_files_in_directory(directory)
    if dirlist is None:
        print("WARN: traverse_directory_tree: get_files_in_directory returned None")
        return []

    for file in dirlist:
        if __debug__:
            print("processing %s" % (file["path"],))
        if file["path"].endswith("/"):
            if __debug__:
                print("%s is a directory -- we must go deeper" % (file["path"],))
            subdirents = traverse_directory_tree(file["path"])
            for i in subdirents:
                if __debug__:
                    print("Appending subdirent %s to my list" % (i["path"],))
                results.append(i)
        else:
            if __debug__:
                print("I spy with my little eye, a file %s" % (file["path"],))
            results.append(file)
    return results


#
# summarize_remote - collect all files on the remote
#    INTERNAL FUNCTION
#    Returns all files on the remote as a hash,
#       retval[remote_filename] = remote_filesize
#    where "remote_filename" is the full path on the remote.
#
def summarize_remote(remote_root):
    if __debug__:
        print("summarize_remote - %s" % (remote_root,))
    all_files = {}
    files = traverse_directory_tree(remote_root)
    for file in files:
        all_files[file["path"]] = file["size"]
    return all_files


#
# find_empty_directories - collect all directories with neither files nor subdirs
#    INTERNAL FUNCTION
#    Returns all directories that could be safely deleted
#    Because they are empty leafs (directories with neither files nor subdirs)
#
def find_empty_directories(directory):
    results = []

    dirlist = get_files_in_directory(directory)
    if len(dirlist) == 0:
        if __debug__:
            print("%s is an empty directory" % (directory,))
        results.append(directory)
    else:
        for file in dirlist:
            if __debug__:
                print("processing %s" % (file["path"],))
            if file["path"].endswith("/"):
                subdirents = find_empty_directories(file["path"])
                for i in subdirents:
                    if __debug__:
                        print("Appending subdirent %s to my list" % (i,))
                    results.append(i)
    return results

##----------------------------------
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
    if __debug__:
        print("root is %s" % (root,))
    result = []
    for file in glob.iglob(root + "/**/*.*", recursive=True):
        for ext in exts:
            if file.lower().endswith(ext):
                result.append(file)
    return result


##----------------------------------
def sync_local_to_remote(remote_root, remote_files, local_files):
    for local_file in local_files:
        remote_file = "%s/%s" % (remote_root, local_file)
        # XXX TODO - Check file sizes - TODO XXX
        #  remote_files[remote_file] is the file size.
        if remote_file in remote_files:
            if __debug__:
                print("OK  %s" % (remote_file,))
            remote_files[remote_file] = -1
        else:
            upload_one_file(local_file, remote_root)


##-------------------------------------------
def operation_sync(remote_root, local_root):
    remote_compound_root = "%s/%s" % (remote_root, local_root)
    remote_files = summarize_remote(remote_compound_root)
    local_files = summarize_local(local_root)

    sync_local_to_remote(remote_root, remote_files, local_files)

    for remote_file in remote_files:
        if remote_files[remote_file] != -1:
            remove_remote_file(remote_file)


def operation_merge(remote_root, local_root):
    remote_root = "%s/%s" % (remote_root, local_root)
    remote_files = summarize_remote(remote_root)
    local_files = summarize_local(local_root)

    sync_local_to_remote(remote_files, local_files)


def operation_remove(remote_root):
    remote_files = summarize_remote(remote_root)
    for file in remote_files:
        if file.startswith(remote_root):
            remove_remote_file(file)


def operation_prune(remote_root):
    done_one = True
    while done_one:
        done_one = False
        empty_directories = find_empty_directories(remote_root)
        for empty_dir in empty_directories:
            if empty_dir.startswith(remote_root):
                remove_remote_empty_directory(empty_dir)
                done_one = True


def operation_list(remote_root):
    remote_files = summarize_remote(remote_root)
    for file in remote_files:
        print("%10d %s" % (remote_files[file], file))


##--------------------------------------------
def usage():
    print("""
Usage: {0} operation ip-address [remote-dir [local-dir [...]]]

Usage Examples:
  {0} sync 192.168.1.155 mymedia/subdir ...
  {0} merge 192.168.1.155 mymedia/subdir ...
  {0} remove 192.168.1.155 /mymedia
  {0} prune 192.168.1.155 /
  {0} list 192.168.1.155 /

 *** IMPORTANT *** README ***
It is important for you to understand that I wrote this utility to manage
entire directory trees at once.  So there are no operations that allow you
to work at the file level.  Maybe someday someone will fork this project and
build awesome file-level control over everything.  But that will not be me.
 *** IMPORTANT *** README ***

Operations
 sync
        Syncs one or more directories on the remote with the local directories
        Files that exist locally but not remotely will be copied over.
        Files that exist remotely but not locally will be removed (from the remote)
        Sync won't remove directories themselves -- use 'prune' for that.
 merge
        Merges one or more directories to the remote.
        The directories will be copied to the place you give on the command line.
        As in the example, stuff would be in /mymedia/subdir/* on the remote.
        Merge never removes any files on the remote
 remove
        Remove the files (but not directories) under a directory on the remote.
        You can remove multiple directories at a time
        To protect you, there is no default. you must provide a directory, even if it is /
        Remove only works on files -- it won't remove empty directories.  Use 'prune' for that.
 prune
        Find and delete any empty directories on the remote.
        You can prune multiple directories at a time
        You don't have to specify a directory. the default is /
        Prune does not remove any files, only empty directories.
 list
        Show you what is on the remote
        You can list multiple directories at a time
        You don't have to specify a directory. the default is /
        This will not change anything on the remote

As an easter egg, you can read the source code to discover more operations which the author
wanted for personal use, but was not sure if a wider audience would find confusing.
    """.format(sys.argv[0],))
    sys.exit(1)


##---------------------------------------------
if len(sys.argv) < 3:
    usage()

operation = sys.argv[1]
init_remote_routes(sys.argv[2])

if operation == "sync" or operation == "xsync" or operation == "update" or operation == "xupdate":
    # "xsync" lets me specify a subdirectory on the remote instead of putting everything under "/".
    # This is because I don't have one unified pile of stuff.
    # I have several distinct trees i store in different places.
    # When I manage my files, i like to create top level subdirectories for each tree.
    # But I am not sure if anybody else would find that useful.
    if operation.startswith("x"):
        if len(sys.argv) < 5:
            usage()
        remote_root = sys.argv[3]
        for local_root in sys.argv[4:]:
            operation_sync(remote_root, local_root)
    else:
        if len(sys.argv) < 4:
            usage()
        for local_root in sys.argv[3:]:
            operation_sync("/", local_root)

elif operation in ["cp", "xcp", "copy", "xcopy", "merge", "xmerge"]:
    # Ditto with "xmerge" -- I use subdirectories to organize independent piles of stuff.
    if operation.startswith("x"):
        if len(sys.argv) < 5:
            usage()
        remote_root = sys.argv[3]
        for local_root in sys.argv[4:]:
            operation_merge(remote_root, local_root)
    else:
        if len(sys.argv) < 4:
            usage()
        for local_root in sys.argv[3:]:
            operation_merge("/", local_root)

elif operation == "rmdir" or operation == "wipe" or operation == "remove" or operation == "empty":
    if len(sys.argv) < 4:
        usage()
    remote_root = sys.argv[3]
    operation_remove(remote_root)

elif operation == "prune":
    if len(sys.argv) < 4:
        operation_prune("/")
    else:
        for remote_root in sys.argv[3:]:
            operation_prune(remote_root)

elif operation == "list":
    if len(sys.argv) < 4:
        operation_list("/")
    else:
        for remote_root in sys.argv[3:]:
            operation_list(remote_root)

else:
    usage()
