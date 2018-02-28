# -*- coding: utf-8 -*-

#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import oslo_messaging as messaging
import os
from oslo_service import periodic_task

from cyborg.accelerator.drivers.fpga.base import FPGADriver
from cyborg.agent.resource_tracker import ResourceTracker
from cyborg.conductor import rpcapi as cond_api
from cyborg.conf import CONF
from cyborg.client.image import glance
from cyborg.client.image import util as img_util
from cyborg.client.placement import placement
from cyborg.client.token import token


class AgentManager(periodic_task.PeriodicTasks):
    """Cyborg Agent manager main class."""

    RPC_API_VERSION = '1.0'
    target = messaging.Target(version=RPC_API_VERSION)

    def __init__(self, topic, host=None):
        super(AgentManager, self).__init__(CONF)
        self.topic = topic
        self.host = host or CONF.host
        self.fpga_driver = FPGADriver()
        self.cond_api = cond_api.ConductorAPI()
        self._rt = ResourceTracker(host, self.cond_api)

    def periodic_tasks(self, context, raise_on_error=False):
        return self.run_periodic_tasks(context, raise_on_error=raise_on_error)

    def hardware_list(self, context, values):
        """List installed hardware."""
        pass

    def get_image_id(self, context, resource_type, requires):
        # (TODO) should sync images
        self._rt._update_image_info()
        return img_util.get_image_uuid_by_match_requirement(
            self._rt.images, resource_type, requires)

    def fpga_program(self, context, accelerator, image_id):
        """ Program a FPGA regoin, image can be a url or local file"""
        # TODO (Shaohe Feng) Get image from glance.
        # And add claim and rollback logical.
        # glance.download_fpga_image(tok, image_id, url)
        tok, data = token.get_token()
        url = token.get_image_url(tok)
        # (TODO) if md5 files exist, and checksum is right, no need to download again
        glance.download_fpga_image(tok, image_id, url,
                                   filepath=img_util.FGPA_IMGAGE_PATH)
        md5 = self._rt.images["images"][image_id]["checksum"]
        if not img_util.download_image_check(image_id, md5, path=img_util.FGPA_IMGAGE_PATH):
            return False
        vendor = self._rt.images["images"][image_id]["vendor"]
        dr = FPGADriver.create(vendor.lower())
        # program VF
        dr.program(accelerator,
                   os.path.join(img_util.FGPA_IMGAGE_PATH, image_id))

        return True
        # raise NotImplementedError()

    @periodic_task.periodic_task(run_immediately=True)
    def update_available_resource(self, context, startup=True):
        """update all kinds of accelerator resources from their drivers."""
        self._rt.update_usage(context)
