# Copyright (c) 2018 Intel.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Track resources like FPGA GPU and QAT for a host.  Provides the
conductor with useful information about availability through the accelerator
model.
"""

import datetime
import socket

# from nova.virt import virtapi
# from nova.virt import driver
from oslo_log import log as logging
from oslo_messaging.rpc.client import RemoteError
from oslo_utils import uuidutils

from cyborg.accelerator.drivers.fpga.base import FPGADriver
from cyborg.common import utils
from cyborg import objects
from cyborg.client.image import glance
from cyborg.client.image import util as img_util
from cyborg.client.placement import placement
from cyborg.client.token import token


LOG = logging.getLogger(__name__)

AGENT_RESOURCE_SEMAPHORE = "agent_resources"
AGENT_IMAGE_SEMAPHORE = "agent_image"

DEPLOYABLE_VERSION = "1.0"

# need to change the driver field name
DEPLOYABLE_HOST_MAPS = {"assignable": "assignable",
                        "pcie_address": "devices",
                        "board": "product_id",
                        "type": "function",
                        "vendor": "vendor_id",
                        "name": "name"}


class ResourceTracker(object):
    """Agent helper class for keeping track of resource usage as instances
    are built and destroyed.
    """

    def __init__(self, host, cond_api):
        # FIXME (Shaohe) local cache for Accelerator.
        # Will fix it in next release.
        self.fpgas = None
        self.host = host
        self.conductor_api = cond_api
        self.fpga_driver = FPGADriver()
        self.images = {
            # should it be image object list? ref: nova/objects/image_meta.py
            "images": {},
            "updated_at": "2000-01-01T00:00:00Z",
            "summary": {}}
        # # we need to load virt driver to get hostname.
        # # ref: "compute/manager.py". Nova use ComputeVirtAPI.
        # # Here we will use virtapi.VirtAPI directly.
        # virtapi = virtapi.VirtAPI()
        # # more driver support see: conf/compute.py, compute_driver option.
        # compute_driver = "libvirt.LibvirtDriver"
        # self.compute_driver = driver.load_compute_driver(virtapi, compute_driver)
        # # it will report:
        # # No handlers could be found for logger "os_brick.initiator.connectors.remotefs"
        # # libvirt:  error : internal error: could not initialize domain event timer
        # # but no harmful for get_hostname()

    @utils.synchronized(AGENT_RESOURCE_SEMAPHORE)
    def claim(self, context):
        pass

    def _fpga_compare_and_update(self, host_dev, acclerator):
        need_updated = False
        for k, v in DEPLOYABLE_HOST_MAPS.items():
            if acclerator[k] != host_dev[v]:
                need_updated = True
                acclerator[k] = host_dev[v]
        return need_updated

    def _gen_deployable_from_host_dev(self, host_dev):
        dep = {}
        for k, v in DEPLOYABLE_HOST_MAPS.items():
            dep[k] = host_dev[v]
        dep["host"] = self.host
        dep["version"] = DEPLOYABLE_VERSION
        dep["availability"] = "free"
        dep["uuid"] = uuidutils.generate_uuid()
        return dep

    @utils.synchronized(AGENT_RESOURCE_SEMAPHORE)
    def update_usage(self, context):
        """Update the resource usage and stats after a change in an
        instance
        """
        def create_deployable(fpgas, bdf, parent_uuid=None):
            fpga = fpgas[bdf]
            dep = self._gen_deployable_from_host_dev(fpga)
            # if parent_uuid:
            dep["parent_uuid"] = parent_uuid
            obj_dep = objects.Deployable(context, **dep)
            new_dep = self.conductor_api.deployable_create(context, obj_dep)
            return new_dep

        fpgas = self._get_fpga_devices()

        fpgas_summary = {}
        for bdf, fpga in fpgas.items():
            if not fpga["assignable"]:
                continue
            vendor = fpga["vendor_id"]
            vendor_summary = fpgas_summary.setdefault(
                vendor, {"PF": 0, "VF": 0})
            if fpga["function"] == 'pf':
                vendor_summary["PF"] += 1
            if fpga["function"] == 'vf':
                vendor_summary["VF"] += 1

        tok, data = token.get_token()
        url = token.get_image_url(tok)
        # images
        self._update_image_info()
        image_infos = img_util.gen_traits_and_resource_type(self.images)
        # NOTE(Shaohe Feng) need more agreement on how to keep consistency.
        self.images["summary"] = image_infos
        # img_util.get_image_uuid_by_match_requirement(
        #     self.images, "C_F_0X8086_PF", ["CRYPTO"])
        # image_id = "bb80583b-a6ae-4cac-9df5-814383c1b32a"
        # glance.download_fpga_image(tok, image_id, url)

        # placement
        # placement_name = self.compute_driver._host.get_hostname()
        url = token.get_placement_url(tok)
        placement_name = socket.gethostname()
        provider_uuid = placement.get_resource_provider_uuid(tok, url, placement_name)
        for vendor, infos in self.images["summary"].items():
            self._update_placement_traits(tok, url, provider_uuid, infos["traits"])

        # self.images["summary"]["INTEL"]["resource"].append("PF")
        for v, i in fpgas_summary.items():
            vendor_name = img_util.vendor_id_to_name(v)
            for fun, num in i.items():
                if num > 0:
                    resource_classes = "_".join(
                        ["CUSTOM", "FPGA", vendor_name, fun.upper()])
                    self._update_placement_resource_class(
                        tok, url, provider_uuid, resource_classes, num)

        bdfs = set(fpgas.keys())
        deployables = self.conductor_api.deployable_get_by_host(
            context, self.host)

        # NOTE(Shaohe Feng) when no "pcie_address" in deployable?
        accls = dict([(v["pcie_address"], v) for v in deployables])
        accl_bdfs = set(accls.keys())

        # Firstly update
        for mutual in accl_bdfs & bdfs:
            accl = accls[mutual]
            if self._fpga_compare_and_update(fpgas[mutual], accl):
                try:
                    self.conductor_api.deployable_update(context, accl)
                except RemoteError as e:
                    LOG.error(e)
        # Add
        new = bdfs - accl_bdfs
        new_pf = set([n for n in new if fpgas[n]["function"] == "pf"])
        for n in new_pf:
            new_dep = create_deployable(fpgas, n)
            accls[n] = new_dep
            sub_vf = set()
            if "regions" in n:
                sub_vf = set([sub["devices"] for sub in fpgas[n]["regions"]])
            for vf in sub_vf & new:
                new_dep = create_deployable(fpgas, vf, new_dep["uuid"])
                accls[vf] = new_dep
                new.remove(vf)
        for n in new - new_pf:
            p_bdf = fpgas[n]["parent_devices"]
            p_accl = accls[p_bdf]
            p_uuid = p_accl["uuid"]
            new_dep = create_deployable(fpgas, n, p_uuid)

        # Delete
        for obsolete in accl_bdfs - bdfs:
            try:
                self.conductor_api.deployable_delete(context, accls[obsolete])
            except RemoteError as e:
                LOG.error(e)
            del accls[obsolete]

    def _get_fpga_devices(self):

        def form_dict(devices, fpgas):
            for v in devices:
                fpgas[v["devices"]] = v
                if "regions" in v:
                    form_dict(v["regions"], fpgas)

        fpgas = {}
        vendors = self.fpga_driver.discover_vendors()
        for v in vendors:
            driver = self.fpga_driver.create(v)
            form_dict(driver.discover(), fpgas)
        return fpgas

    @utils.synchronized(AGENT_IMAGE_SEMAPHORE)
    def _update_image_info(self):
        # import pdb; pdb.set_trace()
        tok, data = token.get_token()
        if not tok:
            return
        url = token.get_image_url(tok)
        if not url:
            return
        query = {"updated_at": "gt:%s" % self.images["updated_at"]}
        r = glance.get_all_fpga_image(tok, url, **query)
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        self.images["updated_at"] = timestamp
        for i in r["images"]:
            if i["id"] not in self.images["images"]:
                self.images["images"].update({i["id"]: i})
        return len(r["images"]) > 0


    def _update_placement_traits(self, tok, url, provider_uuid, traits):
        traits_data = {
            "traits": []
        }
        trs = placement.get_traits(tok, url)
        p_trs = placement.get_resource_provider_traits(tok, url, provider_uuid)
        for t in traits:
            ct = "_".join(["CUSTOM", "CYBORG", t])
            if ct not in trs:
                placement.create_trait(tok, url, ct)
            # just add update
            if ct not in p_trs["traits"]:
                traits_data["traits"].append(ct)

        if traits_data["traits"]:
            traits_data["traits"].extend(p_trs["traits"])
            placement.update_resource_provider_traits(tok, url, provider_uuid, traits_data)

        p_trs = placement.get_resource_provider_traits(tok, url, provider_uuid)
        print p_trs["traits"]

    # add provider code.
    # ref nova: nova/compute/resource_tracker.py
    #     _update call scheduler_client.set_inventory_for_provider

    # provider name ref: get_available_resource
    #    update_available_resource -> _update_available_resource ->
    #    _init_compute_node -> objects.ComputeNode
    # privider inventory ref: get_inventory
    def _update_placement_resource_class(self, tok, url, provider_uuid, resource_classes, num):
        import pdb; pdb.set_trace()
        inventory_data = {
            "allocation_ratio": 1.0,
            "max_unit": num,
            "min_unit": 1,
            "reserved": 0,
            "step_size": 1,
            "total": num
        }
        inventories_data = {"inventories": {}}

        # import pdb; pdb.set_trace()
        if resource_classes:
            exist = placement.get_resource_classe(tok, url, resource_classes)
            print exist
            if not exist:
                placement.create_resource_classe(tok, url, resource_classes)
            placement.get_resource_classe(tok, url, resource_classes)

            exist = placement.get_resource_provider_inventories_resource_class(
                tok, url, provider_uuid, resource_classes)
            if not exist:
                inventories_data["inventories"][resource_classes] = inventory_data
                placement.update_resource_provider_inventories(
                    tok, url, provider_uuid, inventories_data)
            else:
                placement.update_resource_provider_inventories_resource_class(
                    tok, url, provider_uuid, resource_classes)
        placement.get_resource_provider_inventories_resource_class(
            tok, url, provider_uuid, resource_classes)
