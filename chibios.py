class ChibiosPrefixCommand(gdb.Command):
    "Prefix for ChibiOS related helper commands"

    def __init__(self):
        super(ChibiosPrefixCommand, self).__init__("chibios",
                                                   gdb.COMMAND_SUPPORT,
                                                   gdb.COMPLETE_NONE,
                                                   True)

class ChibiosThread(object):
    """Class to model ChibiOS/RT thread"""

    THREAD_STATE = ["READY", "CURRENT", "SUSPENDED", "WTSEM", "WTMTX", "WTCOND", "SLEEPING",
  "WTEXIT", "WTOREVT", "WTANDEVT", "SNDMSGQ", "SNDMSG", "WTMSG", "WTQUEUE", "FINAL"]

    def __init__(self, thread):
        """ Initialize a Thread object. Will throw exceptions if fields do not exist"""
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

        # stklimit and r13 are different pointer types, so cast to get the arithmetic correct
        self._r13 = thread['p_ctx']['r13'].cast(void_p)

        # p_stklimit is optional.
        if 'p_stklimit' in thread.type.keys():
            self._stklimit = thread['p_stklimit'].cast(void_p)

        # only try to dump the stack if we have reasonable confidence that it exists
        if self._stklimit > 0:
            self._stack_size = self._r13 - self._stklimit
            # Try to dump the entire stack of the thread
            inf = gdb.selected_inferior()
            
            try:
                stack = inf.read_memory(self._stklimit, self._stack_size)

                # Find the first non-'U' (0x55) element in the stack space. 
                for i, each in enumerate(stack):
                    if (each != 'U'):
                        break;

                self._stack_unused = i
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
        thread_type = gdb.lookup_type('Thread')

        # Sanity checks on Thread
        if 'p_newer' not in thread_type.keys() or 'p_older' not in thread_type.keys():
            raise gdb.GdbError("ChibiOS/RT thread registry not enabled, cannot access thread information!")
            
        if 'p_stklimit' not in thread_type.keys():
            print "No p_stklimit in Thread struct; enable CH_DBG_ENABLE_STACK_CHECK"

        if 'p_time' not in thread_type.keys():
            print "No p_time in Thread struct; enable CH_DBG_THREADS_PROFILING"

        
    @property
    def name(self):
        return self._name

    @property
    def stack_size(self):
        return self._stack_size

    @property
    def stack_limit(self):
        return self._stklimit

    @property
    def stack_start(self):
        return self._r13

    @property
    def stack_unused(self):
        return self._stack_unused

    @property
    def address(self):
        return self._address

    @property
    def state(self):
        return self._state

    @property
    def flags(self):
        return self._flags

    @property
    def prio(self):
        return self._prio

    @property
    def time(self):
        return self._time


class ChibiosThreadsCommand(gdb.Command):
"""
Print all the ChibiOS threads and their stack usage.

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
        # Make sure Thread has enough info to work with
        ChibiosThread.sanity_check()
        
        # Walk the thread registry
        rlist_p = gdb.parse_and_eval('&rlist')
        rlist_as_thread = rlist_p.cast(gdb.lookup_type('Thread').pointer())
        newer = rlist_as_thread.dereference()['p_newer']
        older = rlist_as_thread.dereference()['p_older']

        print "%-10s %-10s %-10s %6s/%6s %-16s %s" % ("Address",
                                                      "StkLimit",
                                                      "Stack",
                                                      "Free",
                                                      "Total",
                                                      "Name",
                                                      "State")
        while (newer != rlist_as_thread):

            ch_thread = ChibiosThread(newer.dereference())
            print "0x%08x 0x%08x 0x%08x %6d/%6d %-16s %s" % (ch_thread.address,
                                                             ch_thread.stack_limit,
                                                             ch_thread.stack_start,
                                                             ch_thread.stack_unused,
                                                             ch_thread.stack_size,
                                                             ch_thread.name,
                                                             ChibiosThread.THREAD_STATE[ch_thread.state])

            current = newer
            newer = newer.dereference()['p_newer']
            older = newer.dereference()['p_older']

            if (older != current):
                raise gdb.GdbError('Rlist pointer invalid--corrupt list?')


class ChibiosThreadCommand(gdb.Command):
    """Print information about the currently selected thread"""

    def __init__(self):
        super(ChibiosThreadCommand, self).__init__("chibios thread",
                                                    gdb.COMMAND_SUPPORT,
                                                    gdb.COMPLETE_NONE)
    def invoke(self, args, from_tty):
        thread = gdb.selected_thread();
        if thread is not None:
            # inf.ptid is PID, LWID, TID; TID corresponds to the address in
            # memory of the Thread*.
            newer = thread.ptid[2]
            print "%-10s %-10s %-10s %6s/%6s  %s" % ("Address", "StkLimit", "Stack", "Free", "Total", "Name")

            thread_struct = gdb.parse_and_eval('(Thread *)%d' % (newer)).dereference()
            ch_thread = ChibiosThread(thread_struct)
            print "0x%08x 0x%08x 0x%08x %6d/%6d  %s" % (ch_thread.address,
                                                  ch_thread.stack_limit,
                                                  ch_thread.stack_start,
                                                  ch_thread.stack_unused,
                                                  ch_thread.stack_size,
                                                  ch_thread.name)

        else:
            print "No threads found--run info threads first"
            

# class ChibiosTraceCommand(gdb.Command):
#     """ Print the last entries in the trace buffer"""

#     def __init__(self):
#         super(ChibiosTraceCommand, self).__init__("chibios trace",
#                                                   gdb.COMMAND_SUPPORT,
#                                                   gdb.COMPLETE_NONE)

#     def invoke(self, args, from_tty):
#         count = 10
#         if args is not None:
#             count = int(args[0])

#         trace_max = gdb.parse_and_eval(
        

            
ChibiosPrefixCommand()
ChibiosThreadsCommand()
ChibiosThreadCommand()
