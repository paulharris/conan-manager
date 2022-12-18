# conan-manager
Helper script for running conan packagemanager and pinning versions.

## Get-Started Usage
You can find possible commands by calling `./conan-manager.py help`
Then run the script with an action and it'll tell you what parameters it needs.

## Goal
To help conan-v1 build locally across different computers, using consistent package and recipe versions.
This tightly controls the package versioning, without using the lock files.
I couldn't get the hang of lock files, I assume they'll be better in conan v2.

## Future Improvements
Hopefully this will go away in Conan v2, but we shall see.
I threw this together quickly so I could get on with recipe hacking and building my project..
Would be nice to improve argument parsing so it is nicer.  Was first time I used argparse.
And could call conan methods directly via python, instead of calling out to the cmd.
I also don't check the required arguments in all of the actions yet.

## First Step
You have to start somewhere, so build your project manually.
`conan install . -if build`
Personally, to build the first time, I had to do a lot of `--require-override` to:
* use my forks of existing CCI recipes (I was submitting PRs on recipes).
* resolve dependency version clashes.

Once built, there will be a conan.lock file in the install folder (build/, in this case).
Note that this bit hasn't been tested recently, I only had to do this once. I assume it still works.
Capture the versions with:
`conan-manager.py dump_lock --lockfile build/conan.lock > myproject.deps`
The "myproject.deps" will be a json file with all the packages, versions and recipe revisions from the lock file.
Note that I don't think this captures BUILD (tool) requirements, just the pure requirements.

## Build it again
Now you have a "deps" file to use.
To do a `conan install`, run:
`./conan-manager.py conan_install --depfile myproject.deps --profile PATH_TO_PROFILE`
Note that the profile param must be the actual file, eg `~/.conan/profiles/default`
You can also add:
* `--build_missing true` to --build-missing
* `--use_single_profile true` to use `--profile PROFILE`, and not the default: `-pr:b PROFILE -pr:h PROFILE`
(note, 'true' can be anything, even 'false', just need something in that arg, i dunno argparser well enough)
The reason to use a single profile is it seems to help to force the build requirements to use the same versions as your host profile.
There are problems using either single or dual profiles, so sometimes I have to build with single, and sometimes with dual.

## Time to support multiple recipe versions
(you probably will need --remote in these calls too here)
I hack on recipes, so I want past builds to work with the old recipes, AND, be able to build with new recipes for the same version of the package.   Conan v1 will delete past recipe builds when it upgrades the recipe for the same package version.
So, my solution is to put each recipe revision in its own user/channel.
This is done with `upgrade_dep` action, or `upgrade_dep_latest`.
`./conan-manager.py upgrade_dep_latest --depfile myproject.deps --out_depfile myproject-2.deps --depname PACKAGE --depversion PACKVERSION`
You can use the same out-dep-file as the input, to update the file in-place.  Or you can have any number of dep files for different builds.
eg:
`./conan-manager.py upgrade_dep_latest --depfile myproject.deps --out_depfile myproject.deps --depname zlib --depversion 1.3.4`
This will download the latest recipe for `zlib/1.3.4` into the `_/_` (no user/channel), and then conan-copy to a channel called `cci/BIGHASH` where BIGHASH is the recipe revision.  And will update the deps file to specify that exact user/channel + recipe revision.

## Check for upgrades to versions and recipes
`./conan-manager.py check_all_deps --depfile myproject.deps --remote my-remote`
I don't know why I can't pipe the outputs to a file or less, so I just scroll back in the terminal.
Anyway, it'll print out all the requirements you have, and a list of versions on the remotes, pointing to the version you have, and a list of recipe revisions for that version you currently have.

You can also use `check_dep_ver` for a specific version, or `check_dep` for just one dependency from your deps file (using your current version).

`check_all_mainline` helps to check just the packages you haven't pinned to a specific recipe revision yet (ie using `_/_` user/channel).

## conan create
Now you have a way to control your build environment.
If I am hacking on a package recipe, I might have a heap of packages already built for a specific version + recipe that actually can build on my machine.  I went through a long period where the standard CCI recipes would not build without a lot of fixes (it is a lot better now).
So, I clone CCI, `cd myclone/recipes/package/all` and want to run `conan create . package/version`, but I want it to build with the existing packages on my system, and NOT download and build its dependencies fresh.
Do this: `./conan-manager.py conan_create --depfile /PATH/TO/myproject.deps --profile /path/to/profile --depname package --depversion version --depuser user --depchannel channel`
And optionally:
* `--build_missing true`
* `--use_single_profile true` see above notes for this
I usually use `ccitest` for user and `test1` or whatever for channel.
