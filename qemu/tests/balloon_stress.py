import logging
import random
import re
import time

from virttest import utils_misc
from virttest import utils_test
from virttest import error_context
from avocado.core import exceptions
from qemu.tests.balloon_check import BallooningTestWin


@error_context.context_aware
def run(test, params, env):
    """
    Qemu balloon device stress test:
    1) boot guest with balloon device
    2) enable driver verifier in guest
    3) reboot guest (optional)
    4) check device using right driver in guest.
    5) play online video in guest
    6) balloon memory in monitor in loop
    7) kill video process and run it again (option)
    8) check vm alive

    :param test: QEMU test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment.
    """
    def check_video_status(vm):
        """
        Check video playing status

        :param vm: VM object
        :return: return video player process
        """
        error_context.context("Check if video is playing", logging.info)
        target_process = params.get("target_process", "test")
        check_running_cmd = params.get("check_running_cmd", "tasklist")
        s, output = utils_misc.get_guest_cmd_status_output(vm,
                                                           check_running_cmd)
        process = "".join(re.findall(target_process, output, re.M | re.I))
        logging.info("Video process: %s" % process)
        return process

    def run_video(vm):
        """
        Run video in background

        :param vm: VM object
        """
        error_context.context("Run video background", logging.info)
        video_play = utils_misc.InterruptedThread(
            utils_test.run_virt_sub_test, (test, params, env),
            {"sub_type": params.get("video_test")})
        video_play.start()
        if not utils_misc.wait_for(lambda: check_video_status(vm), 240, 10, 2):
            raise exceptions.TestError("Video is not playing")

    def stop_video(vm):
        """
        Stop video

        :param vm: VM object
        """
        video_process = check_video_status(vm)
        if video_process:
            clean_cmd = 'del /f /s "%s"' % video_process
            error_context.context("Stop background video", logging.info)
            session.cmd(clean_cmd)

    error_context.context("Boot guest with balloon device", logging.info)
    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()

    timeout = float(params.get("login_timeout", 360))
    session = vm.wait_for_login(timeout=timeout)

    driver_name = params["driver_name"]
    utils_test.qemu.setup_win_driver_verifier(driver_name, vm, timeout)
    run_video(vm)
    error_context.context("balloon vm memory in loop", logging.info)
    repeat_times = int(params.get("repeat_times", 500))
    time_for_video = float(params.get("time_for_video", 240))
    balloon_test = BallooningTestWin(test, params, env)
    min_sz, max_sz = balloon_test.get_memory_boundary()

    start_time = time.time()
    for i in xrange(repeat_times):
        logging.info("repeat times: %d" % i)
        play_duration = time.time() - start_time
        if play_duration > time_for_video and i < 500:
            stop_video(vm)
            run_video(vm)
            start_time = time.time()
        balloon_test.balloon_memory(int(random.uniform(min_sz, max_sz)))

    error_context.context("verify guest still alive", logging.info)
    vm.verify_alive()
    if session:
        session.close()
