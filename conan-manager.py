#! /usr/bin/python

from packaging import version
import json
import os
import re
import subprocess
import argparse

# https://github.com/conan-io/conan-center-index/pull/14734
# To allow QT to build locally
os.environ["NOT_ON_C3I"] = "1"

re_ref_with_user = re.compile("(.*)/(.*)@(.*)/(.*)#(.*)")
re_ref_without_user = re.compile("(.*)/(.*)#(.*)")
re_pack_ver = re.compile("(.*)/(.*)")


parser = argparse.ArgumentParser()
parser.add_argument('action')
parser.add_argument('--lockfile', type=argparse.FileType('r'))
parser.add_argument('--depfile', type=argparse.FileType('r'))
parser.add_argument('--profile', type=argparse.FileType('r'))

parser.add_argument('--out_depfilename')

# for action check_dep
parser.add_argument('--remote')
parser.add_argument('--depname')
parser.add_argument('--depversion')
parser.add_argument('--deprrev')
parser.add_argument('--depuser')
parser.add_argument('--depchannel')

parser.add_argument('--upload_packages')

# required for bug: https://github.com/conan-io/conan/issues/12437
# ie when building harfbuzz on windows (2022 Nov)
parser.add_argument('--use_single_profile')

parser.add_argument('--build_missing')

# for conan_install, to specify a specific generator
parser.add_argument('--cmake_generator')

args = parser.parse_args()



def check_dep(deps, remote, name):
   TEMPFILE = "conan-check-dep.temp"

   dep = deps[name]
   ver = dep["version"]
   user = dep["user"]
   channel = dep["channel"]
   recipe_rev = dep["recipe_rev"]

   print(f"Current: {name} version: {ver}  user: {user}  channel: {channel}  rrev: {recipe_rev}")
   # print(f"Currently: {name}/{ver}@{user}/{channel}#{recipe_rev}")

   if os.path.exists(TEMPFILE):
      os.remove(TEMPFILE)

   res = subprocess.run(args=[
            "conan",
            "search",
            "--json",
            TEMPFILE,
            "--remote",
            remote,
            f"{name}",
         ]
         , capture_output=True
      )

   if not os.path.exists(TEMPFILE):
      print(f"{name} -- no versions found on remote for this version")
      return

   versions = json.load(open(TEMPFILE))

   print(versions)
   if versions['error'] != False:
      print(f"{name} -- Error checking versions ({versions['error']})")
      return

   if len(versions['results']) == 0:
      print("No remote versions found")
      return

   for ritem in versions['results'][0]['items']:
      m = re_pack_ver.match(ritem["recipe"]["id"])
      if not m:
         raise Exception(f"{name} -- {ritem} -- No name/ver match")
      remote_ver = m.group(2)

      flag = " <--- current" if remote_ver == ver else ""
      print(f"{name} {remote_ver}{flag}")

   #########################################

   if os.path.exists(TEMPFILE):
      os.remove(TEMPFILE)

   res = subprocess.run(args=[
            "conan",
            "search",
            "--revisions",  # get revisions
            "--json",
            TEMPFILE,
            "--remote",
            remote,
            f"{name}/{ver}@" # just look for the base user/channel ... {user}/{channel}",
         ]
         , capture_output=True
      ) # if capture_output=True ... print(res.stdout)

   if not os.path.exists(TEMPFILE):  # {user}/{channel}
      print(f"{name}/{ver}@ -- no revisions found on remote for this version")
      return

   revisions = json.load(open(TEMPFILE))


   current_rev_time = None
   newest_rev_time = None
   newest_rev = None
   for entry in revisions:
      if recipe_rev == entry["revision"]:
         current_rev_time = entry["time"]
   if current_rev_time is None:
      print(f"{name} rev:{recipe_rev} COULD NOT FIND CURRENT REVISION")

   revs = {}
   for entry in revisions:
      # print(f"For remote {rremote['remote']}") # needed if remote == ALL
      rev_time = entry["time"]
      rev = entry["revision"]
      revs[rev_time] = rev
      if current_rev_time is not None and current_rev_time < rev_time and (newest_rev_time is None or newest_rev_time < rev_time):
         newest_rev_time = rev_time
         newest_rev = rev
   for rev in revs:
      flag = " <--- current" if revs[rev] == recipe_rev else ""
      print(f"{name} rev:{rev} @ {revs[rev]}{flag}")
   if newest_rev is None:
      pass
      # print(f"{name} has latest recipe revision @ {current_rev_time}")
   else:
      # print(f"{name} rev:{recipe_rev} @ {current_rev_time}\n --- has newer revision: {newest_rev} @ time {newest_rev_time}")
      print(f"Newer: {newest_rev} @ time {newest_rev_time} -- {name}")
      # else:
         # print(f"{name} has different revision: {rev} @ time {rev_time}")


################################


if args.action == "dump_lock":
   if args.lockfile == None: raise Exception("Requires --lockfile")

   deps = {}

   nodes = json.load(args.lockfile)["graph_lock"]["nodes"]
   for dep in nodes:
      if dep != "0":    # ignore first node - this project
         dep_ref = nodes[dep]["ref"]
         m = re_ref_with_user.match(dep_ref)
         if m:
            pack = m.group(1)
            ver = m.group(2)
            user = m.group(3)
            channel = m.group(4)
            rref = m.group(5)
            deps[pack] = {"version":ver, "user":user, "channel":channel, "recipe_rev":rref}
         else:
            m = re_ref_without_user.match(dep_ref)
            if m:
               pack = m.group(1)
               ver = m.group(2)
               user = "_"
               channel = "_"
               rref = m.group(3)
               deps[pack] = {"version":ver, "user":user, "channel":channel, "recipe_rev":rref}
            else:
               raise Exception("Did not match")

   # print current deps
   print(json.dumps(deps, indent=True, sort_keys=True))


elif args.action == "update_with_lock":
   if args.lockfile == None: raise Exception("Requires --lockfile")
   if args.depfile == None: raise Exception("Need --depfile")
   if args.out_depfilename == None: raise Exception("Need --out_depfilename")

   print(f"Will write update and add to deps file: {args.out_depfilename}")

   deps = json.load(args.depfile)

   nodes = json.load(args.lockfile)["graph_lock"]["nodes"]
   for dep in nodes:
      if dep != "0":    # ignore first node - this project
         dep_ref = nodes[dep]["ref"]
         m = re_ref_with_user.match(dep_ref)
         if m:
            name = m.group(1)
            ver = m.group(2)
            user = m.group(3)
            channel = m.group(4)
            rref = m.group(5)
            deps[name] = {"version":ver, "user":user, "channel":channel, "recipe_rev":rref}
         else:
            m = re_ref_without_user.match(dep_ref)
            if m:
               name = m.group(1)
               ver = m.group(2)
               user = "_"
               channel = "_"
               rref = m.group(3)
               deps[name] = {"version":ver, "user":user, "channel":channel, "recipe_rev":rref}
            else:
               raise Exception("Did not match")

   # print current deps
   with open(args.out_depfilename,"w") as file:
      print(json.dump(deps, file, indent=True, sort_keys=True))


elif args.action == "conan_upload_one":
   if args.depfile == None: raise Exception("Need --depfile")
   if args.depname == None: raise Exception("Need --depname")
   if args.remote == None: raise Exception("Need --remote")
   deps = json.load(args.depfile)
   name = args.depname
   dep = deps[name]
   ver = dep["version"]
   user = dep["user"]
   channel = dep["channel"]
   rrev = dep["recipe_rev"]

   print(f"Uploading {name}/{ver}@{user}/{channel}#{rrev}")

   to_exec=[
            "conan",
            "upload",
            "--check",
            "--remote",
            args.remote,
         ]

   if args.upload_packages:
      to_exec.append("--all")
   to_exec.append(f"{name}/{ver}@{user}/{channel}#{rrev}")

   res = subprocess.run(args=to_exec
         # , capture_output=True
      )



elif args.action == "conan_upload_all":
   if args.depfile == None: raise Exception("Need --depfile")
   if args.remote == None: raise Exception("Need --remote")
   deps = json.load(args.depfile)
   for name in deps:
      dep = deps[name]
      ver = dep["version"]
      user = dep["user"]
      channel = dep["channel"]
      rrev = dep["recipe_rev"]

      print(f"Uploading {name}/{ver}@{user}/{channel}#{rrev}")

      to_exec=[
               "conan",
               "upload",
               "--check",
               "--remote",
               args.remote,
            ]
      if args.upload_packages:
         to_exec.append("--all")
      to_exec.append(f"{name}/{ver}@{user}/{channel}#{rrev}")

      res = subprocess.run(args=to_exec
            # , capture_output=True
         )



elif args.action == "conan_create":
   if args.depfile == None: raise Exception("Need --depfile")
   if args.profile == None: raise Exception("Need --profile")
   if args.depname == None: raise Exception("Need --depname")
   if args.depversion == None: raise Exception("Need --depversion")
   if args.depuser == None: raise Exception("Need --depuser")
   if args.depchannel == None: raise Exception("Need --depchannel")
   print(f"Using profile {args.profile.name}")
   to_exec=[
         "conan", "create",
         ".",
         f"{args.depname}/{args.depversion}@{args.depuser}/{args.depchannel}"
         ]

   if args.build_missing:
       to_exec.extend(["--build", "missing"])

   if args.use_single_profile:
      # required for bug: https://github.com/conan-io/conan/issues/12437
      # ie when building harfbuzz on windows (2022 Nov)
      to_exec.extend(["-pr", args.profile.name])
   else:
      to_exec.extend([
         "-pr:h", args.profile.name,
         "-pr:b", args.profile.name
         ])

   deps = json.load(args.depfile)
   for name in deps:
      if name != args.depname:
         req = deps[name]
         # print(f"Req {name} : {req}")
         to_exec.append("--require-override")
         to_exec.append(f"{name}/{req['version']}@{req['user']}/{req['channel']}#{req['recipe_rev']}")

   # print(f"Will execute: {to_exec}")
   res = subprocess.run(to_exec) # , capture_output=True)
   # print(res.stdout)


elif args.action == "conan_install":
   if args.depfile == None: raise Exception("Need --depfile")
   if args.profile == None: raise Exception("Need --profile")
   print(f"Using profile {args.profile.name}")
   to_exec=[
         "conan", "install",
         ".",
         "-if", "build",
         ]

   if args.build_missing:
       to_exec.extend(["--build", "missing"])

   if args.cmake_generator:
       to_exec.extend(["-c", f"tools.cmake.cmaketoolchain:generator={args.cmake_generator}"])

   if args.use_single_profile:
      # required for bug: https://github.com/conan-io/conan/issues/12437
      # ie when building harfbuzz on windows (2022 Nov)
      to_exec.extend(["-pr", args.profile.name])
   else:
      to_exec.extend([
         "-pr:h", args.profile.name,
         "-pr:b", args.profile.name
         ])

   deps = json.load(args.depfile)
   for name in deps:
      req = deps[name]
      # print(f"Req {name} : {req}")
      to_exec.append("--require-override")
      to_exec.append(f"{name}/{req['version']}@{req['user']}/{req['channel']}#{req['recipe_rev']}")

   print(f"Will execute: {to_exec}")
   res = subprocess.run(to_exec) # , capture_output=True)
   # print(res.stdout)


elif args.action == "print_dep":
   if args.depfile == None: raise Exception("Need --depfile")
   if args.depname == None: raise Exception("Need --depname")
   deps = json.load(args.depfile)
   name = args.depname
   dep = deps[name]
   ver = dep["version"]
   user = dep["user"]
   channel = dep["channel"]
   recipe_rev = dep["recipe_rev"]
   print(f"{name}/{ver}@{user}/{channel}#{recipe_rev}")


elif args.action == "print_all_deps":
   deps = json.load(args.depfile)
   for name in deps:
      dep = deps[name]
      ver = dep["version"]
      user = dep["user"]
      channel = dep["channel"]
      recipe_rev = dep["recipe_rev"]
      print(f"{name}/{ver}@{user}/{channel}#{recipe_rev}")



elif args.action == "upgrade_dep":
   if args.depfile == None: raise Exception("Need --depfile")
   if args.depname == None: raise Exception("Need --depname")
   if args.depversion == None: raise Exception("Need --depversion")
   if args.depuser == None: raise Exception("Need --depuser")
   if args.depchannel == None: raise Exception("Need --depchannel")
   if args.deprrev == None: raise Exception("Need --deprrev")
   deps = json.load(args.depfile)
   deps[args.depname]["version"] = args.depversion
   deps[args.depname]["user"] = args.depuser
   deps[args.depname]["channel"] = args.depchannel
   deps[args.depname]["recipe_rev"] = args.deprrev
   print(json.dumps(deps, indent=True, sort_keys=True))


elif args.action == "upgrade_dep_latest":
   TEMPFILE = "conan-upgrade-dep-latest.temp"
   if args.depfile == None: raise Exception("Need --depfile")
   if args.out_depfilename == None: raise Exception("No out filename")
   if args.depname == None: raise Exception("Need --depname")
   if args.depversion == None: raise Exception("Need --depversion")
   if args.remote == None: raise Exception("Need --remote")

   deps = json.load(args.depfile)
   print(f"Will write new deps file to {args.out_depfilename}")

   name = args.depname
   ver = args.depversion
   if name == None or ver == None: raise Exception("Need name + ver")
   if os.path.exists(TEMPFILE):
      os.remove(TEMPFILE)
   res = subprocess.run(args=[
            "conan",
            "search",
            "--revisions",  # get revisions
            "--json",
            TEMPFILE,
            "--remote",
            args.remote,
            f"{name}/{ver}@",
         ],
         capture_output=True
      )

   if os.path.exists(TEMPFILE):
      with open(TEMPFILE) as file:
         entries = json.load(file)

         if len(entries) > 0:
            entry = entries[0]  # first one is the newest one, it seems
            print(f"Using revision time {entry['time']}")
            recipe_rev = entry["revision"]

            res = subprocess.run(args=[
                     "conan",
                     "download",
                     "--recipe",
                     "-r", args.remote,
                     f"{name}/{ver}@#{recipe_rev}"
                  ]
                  # , capture_output=True
               )

            res = subprocess.run(args=[
                     "conan",
                     "copy",
                     f"{name}/{ver}@#{recipe_rev}",
                     f"cci/{recipe_rev}"
                  ]
                  # , capture_output=True
               )

            res = subprocess.run(args=[
                     "conan",
                     "remove",
                     "-f",
                     f"{name}/{ver}@_/_#{recipe_rev}"
                  ]
                  # , capture_output=True
               )

            deps[name]["version"] = ver
            deps[name]["user"] = "cci"
            deps[name]["channel"] = recipe_rev
            deps[name]["recipe_rev"] = recipe_rev
            with open(args.out_depfilename,"w") as file:
               print(json.dump(deps, file, indent=True, sort_keys=True))


elif args.action == "copy_all_nouserchannel":
   raise Exception("This is a one-time nuclear option, should not be needed going forward...?")
   if args.depfile == None: raise Exception("Need --depfile")
   if args.out_depfilename == None: raise Exception("No out filename")
   print(f"Will write new deps file to {args.out_depfilename}")
   deps = json.load(args.depfile)
   for name in deps:
      print(f"Checking {name}")
      if deps[name]["user"] == "_" and deps[name]["channel"] == "_":
         print(f"COPYING {name}\n")
         ver = deps[name]["version"]
         recipe_rev = deps[name]["recipe_rev"]
         deps[name]["user"] = "cci"
         deps[name]["channel"] = recipe_rev
         res = subprocess.run(args=[
                  "conan",
                  "copy",
                  f"{name}/{ver}@#{recipe_rev}",
                  f"cci/{recipe_rev}"
               ]
               # , capture_output=True
            )
         print("\n\n")
   with open(args.out_depfilename,"w") as file:
      print(json.dump(deps, file, indent=True, sort_keys=True))



elif args.action == "download_dep_to_cciver":
   if args.depname == None: raise Exception("Need --depname")
   if args.depversion == None: raise Exception("Need --depversion")
   if args.deprrev == None: raise Exception("Need --deprrev")
   if args.remote == None: raise Exception("Need --remote")
   name = args.depname
   ver = args.depversion
   recipe_rev = args.deprrev
   # short_rrev = recipe_rev.slice(6) # use 6 chars of the hash as short ident

   res = subprocess.run(args=[
            "conan",
            "download",
            "--recipe",
            "-r", args.remote,
            f"{name}/{ver}@#{recipe_rev}"
         ]
         # , capture_output=True
      )

   res = subprocess.run(args=[
            "conan",
            "copy",
            f"{name}/{ver}@#{recipe_rev}",
            f"cci/{recipe_rev}"
         ]
         # , capture_output=True
      )


# check newer recipe revisions for a particular version
elif args.action == "check_dep_ver":
   TEMPFILE = "conan-check-dep-ver.temp"
   if args.depname == None: raise Exception("Need --depname")
   if args.depversion == None: raise Exception("Need --depversion")
   if args.remote == None: raise Exception("Need --remote")
   name = args.depname
   ver = args.depversion
   print(f"Checking dependency {name}/{ver}@")

   if os.path.exists(TEMPFILE):
      os.remove(TEMPFILE)
   res = subprocess.run(args=[
            "conan",
            "search",
            "--revisions",  # get revisions
            "--json",
            TEMPFILE,
            "--remote",
            args.remote,
            f"{name}/{ver}@",
         ],
         capture_output=True
      )

   if os.path.exists(TEMPFILE):
      # if capture_output=True ... print(res.stdout)
      # print("searched, found: ")
      with open(TEMPFILE) as file:
         entries = json.load(file)
         current_rev_time = None
         newest_rev_time = None
         newest_rev = None

         for entry in entries:
            rev_time = entry["time"]
            rev = entry["revision"]
            print(f"{name} rev:{rev} @ {rev_time}")
   else:
      print(f"{name}/{ver}@ -- no revisions found on remote for this version")


elif args.action == "check_all_mainline":
   if args.depfile == None: raise Exception("Need --depfile")
   deps = json.load(args.depfile)
   for name in deps:
      dep = deps[name]
      ver = dep["version"]
      recipe_rev = dep["recipe_rev"]
      user = dep["user"]
      channel = dep["channel"]
      if user == "_" and channel == "_":
         print(f"Dep has no user/channel: {name}/{ver}@")


elif args.action == "check_dep":
   if args.depfile == None: raise Exception("Need --depfile")
   if args.remote == None: raise Exception("Need --remote")
   if args.depname == None: raise Exception("Need --depname")

   deps = json.load(args.depfile)
   check_dep(deps, args.remote, args.depname)



# check newer recipe revisions for current version
elif args.action == "check_all_deps":
   if args.depfile == None: raise Exception("Need --depfile")
   if args.remote == None: raise Exception("Need --remote")
   deps = json.load(args.depfile)
   for name in sorted(deps):
      check_dep(deps, args.remote, name)
      print("\n\n")


else:
   print("""
Invalid action
Options:
    dump_lock
    update_with_lock

    conan_upload_one
    conan_upload_all

    conan_create
    conan_install

    print_dep
    print_all_deps

    upgrade_dep
    upgrade_dep_latest

    copy_all_nouserchannel

    download_dep_to_cciver

    check_dep_ver
    check_all_mainline
    check_dep
    check_all_deps
   """)


# # check newer versions for pack
# elif False:
#    for dep in deps:
#       dep = deps[pack]
#       current_ver = dep["version"]
#       # print(f"{pack} : {dep['version']} : {dep['user']} : {dep['channel']} : {dep['rref']}")
#       if os.path.exists(TEMPFILE):
#          os.remove(TEMPFILE)
#       res = subprocess.run(args=["conan", "search", "--json", TEMPFILE, "--remote", REMOTE, pack], capture_output=True)
#       # if capture_output=True ... print(res.stdout)
#       # print("searched, found: ")
#       with open(TEMPFILE) as file:
#          j = json.load(file)
#          if j["error"] != False:
#             raise Exception(f"There was an error, check {TEMPFILE}")
#          for rremote in j["results"]:
#             # print(f"For remote {rremote['remote']}") # needed if remote == ALL
#             for ritem in rremote["items"]:
#                m = re_pack_ver.match(ritem["recipe"]["id"])
#                if not m:
#                   raise Exception("No pack/ver match")
#                ver = m.group(2)
#                # print(f"Version {ver}")
#                if version.parse(current_ver) < version.parse(ver):
#                   print(f"{pack} found newer version {current_ver} < {ver}")
