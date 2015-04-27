"""
Copyright (c) 2012-2013 RockStor, Inc. <http://rockstor.com>
This file is part of RockStor.

RockStor is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published
by the Free Software Foundation; either version 2 of the License,
or (at your option) any later version.

RockStor is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

"""
Disk view, for anything at the disk level
"""

from rest_framework.response import Response
from django.db import transaction
from storageadmin.models import (Disk, SMARTInfo, SMARTAttribute,
                                 SMARTCapability)
from fs.btrfs import (scan_disks, wipe_disk, blink_disk, enable_quota,
                      btrfs_uuid, pool_usage, mount_root)
from storageadmin.serializers import SMARTInfoSerializer
from storageadmin.util import handle_exception
from django.conf import settings
import rest_framework_custom as rfc
from system import smart
from datetime import datetime
from django.utils.timezone import utc
from django.db.models import Count

import logging
logger = logging.getLogger(__name__)


class DiskSMARTView(rfc.GenericView):
    serializer_class = SMARTInfoSerializer

    def _validate_disk(self, dname, request):
        try:
            return Disk.objects.get(name=dname)
        except:
            e_msg = ('Disk: %s does not exist' % dname)
            handle_exception(Exception(e_msg), request)

    def get_queryset(self, *args, **kwargs):
        #do rescan on get.
        with self._handle_exception(self.request):
            if ('dname' in kwargs):
                self.paginate_by = 0
                disk = self._validate_disk(kwargs['dname'], self.request)
                try:
                    return SMARTInfo.objects.filter(disk=disk).order_by('-toc')[0]
                except:
                    return []
                distinct_fields = SMARTAttribute.objects.values('name').annotate(c=Count('name'))
                qs = []
                for d in distinct_fields:
                    qs.append(SMARTAttribute.objects.filter(**{'name': d['name'], 'disk': disk}).order_by('-toc')[0])
                return qs
            #return SMARTAttribute.objects.filter()
            return SMARTInfo.objects.filter().order_by('-toc')

    @transaction.commit_on_success
    def _info(self, disk):
        #fetch info from smartctl -a /dev/dname
        attributes = smart.extended_info(disk.name)
        capabilities = smart.capabilities(disk.name)
        logger.debug('capabilities = %s' % capabilities)
        ts = datetime.utcnow().replace(tzinfo=utc)
        si = SMARTInfo(disk=disk, toc=ts)
        si.save()
        sas = []
        for k in attributes:
            t = attributes[k]
            sa = SMARTAttribute(info=si, aid=t[0], name=t[1], flag=t[2],
                                normed_value=t[3], worst=t[4], threshold=t[5],
                                atype=t[6], updated=t[7], failed=t[8],
                                raw_value=t[9])
            sa.save()
            sas.append(sa)
        for c in capabilities:
            t = capabilities[c]
            sc = SMARTCapability(info=si, name=c, flag=t[0], capabilities=t[1])
            sc.save()
        return Response(SMARTInfoSerializer(si).data)

    def post(self, request, dname, command):
        with self._handle_exception(request):
            disk = self._validate_disk(dname, request)
            if (command == 'info'):
                return self._info(disk)
            e_msg = ('Unknown command: %s. Only valid commands are scan, '
                     'wipe' % command)
            handle_exception(Exception(e_msg), request)
