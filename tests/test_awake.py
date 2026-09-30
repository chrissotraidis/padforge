"""While a build runs PadMint keeps the computer awake and, on Windows, stops a click
in the window from pausing the build. Best-effort: nothing here may stop a build."""
import ctypes
import unittest
from unittest import mock

from padmint import awake


def windows_kernel(mode_value=0x1F7):
    kernel = mock.Mock()
    kernel.SetThreadExecutionState.return_value = 1
    kernel.GetStdHandle.return_value = 0x50
    kernel.SetConsoleMode.return_value = 1

    def get_mode(_handle, pointer):
        pointer._obj.value = mode_value
        return 1
    kernel.GetConsoleMode.side_effect = get_mode
    return kernel


class WhileBuildingTests(unittest.TestCase):
    def windows(self, kernel):
        return [mock.patch.object(awake.sys, "platform", "win32"),
                mock.patch.object(ctypes, "WinDLL", create=True, return_value=kernel)]

    def test_windows_stays_awake_and_quick_edit_is_off_only_while_building(self):
        kernel = windows_kernel()
        patches = self.windows(kernel)
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with awake.while_building():
            kernel.SetThreadExecutionState.assert_called_once_with(
                awake.ES_CONTINUOUS | awake.ES_SYSTEM_REQUIRED)
            self.assertEqual(kernel.SetConsoleMode.call_args.args[1], 0x1F7 & ~0x40)
        self.assertEqual(kernel.SetThreadExecutionState.call_args.args, (awake.ES_CONTINUOUS,))
        self.assertEqual(kernel.SetConsoleMode.call_args.args[1], 0x1F7)

    def test_quick_edit_already_off_is_left_alone(self):
        kernel = windows_kernel(0x1B7)
        patches = self.windows(kernel)
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with awake.while_building():
            pass
        kernel.SetConsoleMode.assert_not_called()

    def test_a_failing_call_does_not_stop_the_build(self):
        with mock.patch.object(awake.sys, "platform", "win32"), \
                mock.patch.object(ctypes, "WinDLL", create=True, side_effect=OSError("no kernel32")):
            with awake.while_building():
                ran = True
        self.assertTrue(ran)

    def test_mac_runs_caffeinate_for_this_process_and_stops_it_after(self):
        process = mock.Mock()
        with mock.patch.object(awake.sys, "platform", "darwin"), \
                mock.patch.object(awake.shutil, "which", return_value="/usr/bin/caffeinate"), \
                mock.patch.object(awake.os, "getpid", return_value=4242), \
                mock.patch.object(awake.subprocess, "Popen", return_value=process) as popen:
            with self.assertRaises(RuntimeError):
                with awake.while_building():
                    self.assertEqual(popen.call_args.args[0], ["/usr/bin/caffeinate", "-i", "-w", "4242"])
                    process.terminate.assert_not_called()
                    raise RuntimeError("build stopped")
        process.terminate.assert_called_once_with()

    def test_mac_without_caffeinate_and_linux_do_nothing(self):
        for platform, which in (("darwin", None), ("linux", "/usr/bin/caffeinate")):
            with mock.patch.object(awake.sys, "platform", platform), \
                    mock.patch.object(awake.shutil, "which", return_value=which), \
                    mock.patch.object(awake.subprocess, "Popen") as popen:
                with awake.while_building():
                    pass
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
