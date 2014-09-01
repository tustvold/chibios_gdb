from __future__ import print_function

import gdb


class ChibiosPrefixCommand(gdb.Command):
    """Prefix for ChibiOS related helper commands"""
    def __init__(self):
        super(ChibiosPrefixCommand, self).__init__("chibios",
                                                   gdb.COMMAND_SUPPORT,
                                                   gdb.COMPLETE_NONE,
                                                   True)

# List of all information to print for threads
# Format is: <header_formatter> <header_title> <value_formatter>
THREAD_INFO = [("{:10}", "Address", "{thread.address:#10x}"),
               ("{:10}", "StkLimit", "{thread.stack_limit:#10x}"),
               ("{:10}", "Stack", "{thread.stack_start:#10x}"),
               ("{:>6}", "Free", "{thread.stack_unused:6}"),
               ("{:>6}", "Total", "{thread.stack_size:6}"),
               ("{:16}", "Name", "{thread.name:16}"),
               ("{:10}", "State", "{thread.state_str}")]

# Build the string for thread info header
THREAD_INFO_HEADER_STRING = " ".join(each[0] for each in THREAD_INFO)
THREAD_INFO_HEADER_DATA = [each[1] for each in THREAD_INFO]
THREAD_INFO_HEADER = THREAD_INFO_HEADER_STRING.format(*THREAD_INFO_HEADER_DATA)

# Build format string for thread info rows.
THREAD_INFO = " ".join(each[2] for each in THREAD_INFO)


class ChibiosThread(object):
    """Class to model ChibiOS/RT thread"""
    THREAD_STATE = ["READY", "CURRENT", "SUSPENDED", "WTSEM", "WTMTX",
                    "WTCOND", "SLEEPING", "WTEXIT", "WTOREVT",
                    "WTANDEVT", "SNDMSGQ", "SNDMSG", "WTMSG",
                    "WTQUEUE", "FINAL"]

    def __init__(self, thread):
        """ Initialize a Thread object. Will throw exceptions if fields do not
        exist

        """
        self._stklimit = 0
        self._r13 = 0
        self._address = 0
        self._stack_size = 0
        self._stack_unused = 0
        self._name = "<no name>"
        self._state = 0
        self._flags = 0
        self._prio = 0
        self._refs = 0
        self._time = 0

        # Extract all thread information
        # Get a gdb.Type which is a void pointer.
        void_p = gdb.lookup_type('void').pointer()

        # stklimit and r13 are different pointer types, so cast to get the
        # arithmetic correct
        self._r13 = thread['p_ctx']['r13'].cast(void_p)

        # p_stklimit is optional.
        if 'p_stklimit' in thread.type.keys():
            self._stklimit = thread['p_stklimit'].cast(void_p)

        # only try to dump the stack if we have reasonable confidence that it
        # exists
        if self._stklimit > 0:
            self._stack_size = self._r13 - self._stklimit
            # Try to dump the entire stack of the thread
            inf = gdb.selected_inferior()

            try:
                stack = inf.read_memory(self._stklimit, self._stack_size)

                # Find the first non-'U' (0x55) element in the stack space.
                for i, each in enumerate(stack):
                    if (each != 'U'):
                        self._stack_unused = i
                        break
                else:
                    # Everything is 'U', apparently.
                    self._stack_unused = self._stack_size

            except gdb.MemoryError:
                self._stack_unused = 0

        else:
            self._stack_size = 0
            self._stack_unused = 0

        self._address = thread.address

        if len(thread['p_name'].string()) > 0:
            self._name = thread['p_name'].string()

        self._state = int(thread['p_state'])
        self._flags = thread['p_flags']
        self._prio = thread['p_prio']
        self._refs = thread['p_refs']

        # p_time is optional
        if 'p_time' in thread.type.keys():
            self._time = thread['p_time']

    @staticmethod
    def sanity_check():
        """Check to see if ChibiOS/RT has been built with enough debug
        information to read thread information.
        """
        thread_type = gdb.lookup_type('Thread')

        # Sanity checks on Thread
        # From http://stackoverflow.com/questions/1285911/python-how-do-i-check-that-multiple-keys-are-in-a-dict-in-one-go
        if not all(k in thread_type.keys() for k in ("p_newer", "p_older")):
            raise gdb.GdbError("ChibiOS/RT thread registry not enabled, cannot"
                               " access thread information!")

        if 'p_stklimit' not in thread_type.keys():
            print("No p_stklimit in Thread struct; enable"
                  " CH_DBG_ENABLE_STACK_CHECK")

        if 'p_time' not in thread_type.keys():
            print("No p_time in Thread struct; enable"
                  " CH_DBG_THREADS_PROFILING")

    @property
    def name(self):
        return self._name

    @property
    def stack_size(self):
        return long(self._stack_size)

    @property
    def stack_limit(self):
        return long(self._stklimit)

    @property
    def stack_start(self):
        return long(self._r13)

    @property
    def stack_unused(self):
        return long(self._stack_unused)

    @property
    def address(self):
        return long(self._address)

    @property
    def state(self):
        return self._state

    @property
    def state_str(self):
        return ChibiosThread.THREAD_STATE[self.state]

    @property
    def flags(self):
        return self._flags

    @property
    def prio(self):
        return self._prio

    @property
    def time(self):
        return self._time


def chibios_get_threads():
    """ Create a list of ChibiosThreads for all threads currently in
    the system

    """
    # Make sure Thread has enough info to work with
    ChibiosThread.sanity_check()

    threads = []

    # Walk the thread registry
    rlist_p = gdb.parse_and_eval('&rlist')
    rlist_as_thread = rlist_p.cast(gdb.lookup_type('Thread').pointer())
    newer = rlist_as_thread.dereference()['p_newer']
    older = rlist_as_thread.dereference()['p_older']

    while (newer != rlist_as_thread):
        ch_thread = ChibiosThread(newer.dereference())
        threads.append(ch_thread)

        current = newer
        newer = newer.dereference()['p_newer']
        older = newer.dereference()['p_older']

        if (older != current):
            raise gdb.GdbError('Rlist pointer invalid--corrupt list?')

    return threads


class ChibiosThreadsCommand(gdb.Command):
    """Print all the ChibiOS threads and their stack usage.

    This will not work if ChibiOS was not compiled with, at a minumum,
    CH_USE_REGISTRY. Additionally, CH_DBG_ENABLE_STACK_CHECK and
    CH_DBG_FILL_THREADS are necessary to compute the used/free stack
    for each thread.
    """
    def __init__(self):
        super(ChibiosThreadsCommand, self).__init__("chibios threads",
                                                    gdb.COMMAND_SUPPORT,
                                                    gdb.COMPLETE_NONE)

    def invoke(self, args, from_tty):
        threads = chibios_get_threads()

        if threads is not None:
            print(THREAD_INFO_HEADER)
            for thread in threads:
                print(THREAD_INFO.format(thread=thread))


class ChibiosThreadCommand(gdb.Command):
    """Print information about the currently selected thread"""
    def __init__(self):
        super(ChibiosThreadCommand, self).__init__("chibios thread",
                                                   gdb.COMMAND_SUPPORT,
                                                   gdb.COMPLETE_NONE)

    def invoke(self, args, from_tty):
        thread = gdb.selected_thread()
        if thread is not None:
            threads = chibios_get_threads()

            # inf.ptid is PID, LWID, TID; TID corresponds to the address in
            # memory of the Thread*.
            newer = thread.ptid[2]

            ch_thread = next((i for i in threads if i.address == newer), None)
            if ch_thread is not None:
                print(THREAD_INFO_HEADER)
                print(THREAD_INFO.format(thread=ch_thread))
            else:
                print("Invalid thread")

        else:
            print("No threads found--run info threads first")


class ChibiosTraceCommand(gdb.Command):
    """Print the last entries in the trace buffer"""

    def __init__(self):
        super(ChibiosTraceCommand, self).__init__("chibios trace",
                                                  gdb.COMMAND_SUPPORT,
                                                  gdb.COMPLETE_NONE)

    def trace_line(self, index, time, state, prev_thread, curr_thread):
        """Return a formatted string for a single trace"""
        trace_format = "{:6} {:8d} {:#10x} {:16} {:10} {:#10x} {:16}"
        if prev_thread is None:
            return trace_format.format(index,
                                       time,
                                       0,
                                       "",
                                       ChibiosThread.THREAD_STATE[state],
                                       curr_thread.address,
                                       curr_thread.name)
        else:
            return trace_format.format(index,
                                       time,
                                       prev_thread.address,
                                       prev_thread.name,
                                       ChibiosThread.THREAD_STATE[state],
                                       curr_thread.address,
                                       curr_thread.name)

    def invoke(self, args, from_tty):
        argv = gdb.string_to_argv(args)
        if (len(argv) > 0):
            count = int(argv[0])
        else:
            count = 10

        threads = chibios_get_threads()

        try:
            dbg_trace_buffer = gdb.parse_and_eval("dbg_trace_buffer")
        except gdb.error:
            raise gdb.GdbError("Debug Trace Buffer not found. Compile with"
                               " CH_DBG_ENABLE_TRACE")

        trace_buffer_size = int(dbg_trace_buffer['tb_size'])

        if (count > trace_buffer_size):
            count = trace_buffer_size

        trace_buffer = dbg_trace_buffer['tb_buffer']

        current_trace = dbg_trace_buffer['tb_ptr']

        trace_start = int(current_trace.dereference().address -
                          trace_buffer.dereference().address)

        traces = []

        for i in xrange(trace_start, trace_buffer_size):
            traces.append(trace_buffer[i])

        for i in xrange(0, trace_start):
            traces.append(trace_buffer[i])

        print("{:>6} {:>8} {:10} {:16} {:10} {:10} {:16}".format("Event",
                                                                 "Time",
                                                                 "Previous",
                                                                 "Name",
                                                                 "State",
                                                                 "Current",
                                                                 "Name"))

        trace_lines = []

        # Print oldest trace separately since we don't have previous
        # information
        thread = next((i for i in threads if
                       i.address == long(traces[0]['se_tp'])), None)
        trace_lines.append(self.trace_line(-63,
                                           int(traces[0]['se_time']),
                                           int(traces[0]['se_state']),
                                           None,
                                           thread))

        for j, event in enumerate(traces[1:], 1):
            curr_thread = next((i for i in threads if
                                i.address == long(event['se_tp'])), None)
            prev_thread = next((i for i in threads if
                                i.address == long(traces[j - 1]['se_tp'])), None)
            trace_lines.append(self.trace_line(-63 + j,
                                               int(event['se_time']),
                                               int(event['se_state']),
                                               prev_thread,
                                               curr_thread))

        for trace in trace_lines[-count:]:
            print(trace)


class ChibiosInfoCommand(gdb.Command):
    """Print information about ChibiOS/RT"""
    def __init__(self):
        super(ChibiosInfoCommand, self).__init__("chibios info",
                                                 gdb.COMMAND_SUPPORT,
                                                 gdb.COMPLETE_NONE)

    def invoke(self, args, from_tty):
        try:
            ch_debug = gdb.parse_and_eval('ch_debug')
        except gdb.error:
            raise gdb.GdbError("Could not find ch_debug")

        ch_version = int(ch_debug['ch_version'])
        ch_major = (ch_version >> 11) & 0x1f
        ch_minor = (ch_version >> 6) & 0x1f
        ch_patch = (ch_version & 0x1f)

        print("ChibiOS/RT version {}.{}.{}".format(ch_major,
                                                   ch_minor,
                                                   ch_patch))


class ChibiosTimersCommand(gdb.Command):
    """Print current timers. Partially unimplemented"""
    def __init__(self):
        super(ChibiosTimersCommand, self).__init__("chibios timers",
                                                   gdb.COMMAND_SUPPORT,
                                                   gdb.COMPLETE_NONE)

    def invoke(self, args, from_tty):
        vtlist_p = gdb.parse_and_eval('&vtlist')

        vtlist_as_timer = vtlist_p.cast(gdb.lookup_type("VirtualTimer").pointer())

        vt_next = vtlist_as_timer.dereference()['vt_next']
        vt_prev = vtlist_as_timer.dereference()['vt_prev']

        print("{:6} {:10} {:10}".format("Time",
                                        "Callback",
                                        "Param"))

        while (vt_next != vtlist_as_timer):
            vt_time = int(vt_next.dereference()['vt_time'])
            vt_func = long(vt_next.dereference()['vt_func'])
            vt_par = long(vt_next.dereference()['vt_par'])
            print("{:6} {:#10x} {:#10x}".format(vt_time,
                                                vt_func,
                                                vt_par))

            current = vt_next
            vt_next = vt_next.dereference()['vt_next']
            vt_prev = vt_next.dereference()['vt_prev']

            if (vt_prev != current):
                raise gdb.GdbError('Rlist pointer invalid--corrupt list?')


ChibiosPrefixCommand()
ChibiosThreadsCommand()
ChibiosThreadCommand()
ChibiosTraceCommand()
ChibiosInfoCommand()
ChibiosTimersCommand()
