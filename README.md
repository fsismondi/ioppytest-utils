# Contact

Federico Sismondi
Contact address: federicosismondi(AT)gmail(DOT)com

# Utils

This repo provides some libs and snippets in the form of python modules
used by several ioppytest components and F-Interop components.

## Installing CLI, lib and other components:

pip install 

## For contributing or directly using the source code:
Libraries in this repo are all self contained what makes it easy to
import.
There are several approaches for doing so:

1. Simply copy & paste the code into your python modules.
Any modification on the libraries must be done into
[utils repo](https://gitlab.f-interop.eu/f-interop-contributors/utils)
Please increase the VERSION number when doing so.

2. Submodule it:
From the top dir of your git repo run:
```
git submodule add https://gitlab.f-interop.eu/f-interop-contributors/utils.git <someSubDir>/utils
```

commit & push
```
git commit -m 'added f-interop's utils git repo as submodule'
```

remember when cloning a project with submodules to use --recursive flag
```
git clone --recursive ...
```

or else, right after cloning you can:
```
git submodule update --init --recursive
```

whenever you find that your utils libraries are not the latests versions
you can 'bring' those last changes from the main utils repo to your project
with:
```
git submodule update --remote --merge
```

after bringing the last changes you can update your project with the last changes by doing:
```
git add <someSubDir>/utils
git commit -m 'updated submodule reference to last commit'
git push
```
