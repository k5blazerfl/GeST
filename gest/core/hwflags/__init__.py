"""Hardware-derived USE_EXPAND flags: CPU_FLAGS_X86 and VIDEO_CARDS.

The Handbook detects the CPU's instruction sets with ``cpuid2cpuflags`` and the
GPU vendor, then writes ``package.use`` drop-ins. GeST does the same, but owns
its *own* numbered fragments — ``package.use/50gest-cpuflags`` and
``package.use/50gest-videocards`` — so re-running detection is idempotent and
never fights a hand-written file (design open question #3).

Detection is unprivileged (``cpuid2cpuflags`` / ``lspci``); the fragments are
written through the Portage ``WriteConfig`` RPC.
"""
