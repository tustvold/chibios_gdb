# ChibiOS GDB

This is a python script designed to emulate the debugging features of
ChibiStudio using only GDB with python extensions. Currently, thread
debugging (including unused stack calculation) and the debug trace buffer
are fully supported; timers are partially implemented.


# Requirements

This script requires a copy of arm-none-eabi-gdb which was built with
Python support. Unfortunately, the gdb shipped with gcc-arm-embedded does
*not* have Python enabled; I cannot comment on the state of python support
in other toolchains. Users willing to build a copy of arm-none-eabi-gdb
from source can do so, ensuring that --with-python=yes is used during
configuration..


# Usage

Source the chibios.py script in gdb:

```
(gdb) source /path/to/chibios.py
```

You can then use the following commands:

* chibios info - Print the version of ChibiOS/RT
* chibios threads - Print all threads (equivalent to the "threads" tab of
ChibiStudio)
* chibios thread - Print the current selected thread (Requires OpenOCD with
ChibiOS/RT support)
* chibios trace [count] - Print the last *count* entries of the trace
buffer; if not specified, defaults to 10

# TODOs

* Fix timer support
* Have 'chibios thread' fall back to using currp when not in OpenOCD
* More error checking on linked lists, etc.
