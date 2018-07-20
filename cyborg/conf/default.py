# Copyright 2017 Huawei Technologies Co.,LTD.
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

import os
import socket

from oslo_config import cfg
from keystoneauth1 import loading as k_loading

from cyborg.common.i18n import _
from cyborg.conf import utils as confutils


exc_log_opts = [
    cfg.BoolOpt('fatal_exception_format_errors',
                default=False,
                help=_('Used if there is a formatting error when generating '
                       'an exception message (a programming error). If True, '
                       'raise an exception; if False, use the unformatted '
                       'message.')),
]

service_opts = [
    cfg.HostAddressOpt('host',
                       default=socket.getfqdn(),
                       sample_default='localhost',
                       help=_('Name of this node. This can be an opaque '
                              'identifier. It is not necessarily a hostname, '
                              'FQDN, or IP address. However, the node name '
                              'must be valid within an AMQP key, and if using '
                              'ZeroMQ, a valid hostname, FQDN, or IP address.')
                       ),
    cfg.IntOpt('periodic_interval',
               default=60,
               help=_('Default interval (in seconds) for running periodic '
                      'tasks.')),
]

path_opts = [
    cfg.StrOpt('pybasedir',
               default=os.path.abspath(
                   os.path.join(os.path.dirname(__file__), '../')),
               sample_default='/usr/lib/python/site-packages/cyborg/cyborg',
               help=_('Directory where the cyborg python module is '
                      'installed.')),
    cfg.StrOpt('bindir',
               default='$pybasedir/bin',
               help=_('Directory where cyborg binaries are installed.')),
    cfg.StrOpt('state_path',
               default='$pybasedir',
               help=_("Top-level directory for maintaining cyborg's state.")),
]

PLACEMENT_CONF_SECTION = 'placement'
DEFAULT_SERVICE_TYPE = 'placement'

placement_group = cfg.OptGroup(
    PLACEMENT_CONF_SECTION,
    title='Placement Service Options',
    help="Configuration options for connecting to the placement API service")

placement_opts = [
    cfg.StrOpt('endpoint_type',
               default='public',
               choices=['public', 'admin', 'internal'],
               help=_('Type of the placement endpoint to use.  This endpoint '
                      'will be looked up in the keystone catalog and should '
                      'be one of public, internal or admin.')),
    cfg.BoolOpt(
        'randomize_allocation_candidates',
        default=False,
        help=_('If True, when limiting allocation candidate results, the '
               'results will be a random sampling of the full result set. '
               'If False, allocation candidates are returned in a '
               'deterministic but undefined order. That is, all things '
               'being equal, two requests for allocation candidates will '
               'return the same results in the same order; but no guarantees '
               'are made as to how that order is determined.')),
]


def register_opts(conf):
    conf.register_opts(exc_log_opts)
    conf.register_opts(service_opts)
    conf.register_opts(path_opts)


def register_placement_opts(cfg=cfg.CONF):
    cfg.register_group(placement_group)
    cfg.register_opts(placement_opts, group=PLACEMENT_CONF_SECTION)
    confutils.register_ksa_opts(cfg, placement_group, DEFAULT_SERVICE_TYPE)


DEFAULT_OPTS = (exc_log_opts + service_opts + path_opts)
PLACEMENT_OPTS = (placement_opts)


def list_opts():
    return {
        PLACEMENT_CONF_SECTION: (
            placement_opts +
            k_loading.get_session_conf_options() +
            k_loading.get_auth_common_conf_options() +
            k_loading.get_auth_plugin_conf_options('password') +
            k_loading.get_auth_plugin_conf_options('v2password') +
            k_loading.get_auth_plugin_conf_options('v3password') +
            confutils.get_ksa_adapter_opts(DEFAULT_SERVICE_TYPE)),
        'DEFAULT': DEFAULT_OPTS
    }
