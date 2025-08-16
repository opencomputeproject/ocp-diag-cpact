"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

from abc import ABC, abstractmethod
from utils.logger_utils import TestLogger

class BaseExecutor(ABC):
    def __init__(self, step: dict, context, executor=None, validate_continue=False):
        self.logger = TestLogger().get_logger()
        self.logger.info(f"Initializing {self.__class__.__name__} with step: {step}")
        self.step = step
        self.context = context
        self.thread_executor = executor
        self.validate_continue = validate_continue

    @abstractmethod
    def execute(self):
        pass
