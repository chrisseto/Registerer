import os
import json
import logging
import httplib as http

from tornado import web
from tornado.gen import coroutine

from archiver import settings
from archiver.util import signing
from archiver.backend import store
from archiver.datatypes import Container
from archiver.exceptions import ValidationError

from utils import BaseAPIHandler, push_task


logger = logging.getLogger(__name__)


def collect_handlers():
    return [
        (os.path.join(settings.URL_PREFIX, klass.URL), klass)
        for klass in
        BaseAPIHandler.__subclasses__()
    ]


class ArchiveHandler(BaseAPIHandler):
    URL = r'archives/?'

    def get(self):
        self.write({'containers': store.list_containers()})

    def put(self):
        if not signing.verify_callback(self.json):
            logger.warn('Incorrectly signed callback from %s' %
                        self.request.remote_ip)
            raise HTTPError(http.UNAUTHORIZED)

        #Load up our json for pretty logging
        self.json['reasons'] = ', '.join(self.json.get('reasons', []))
        self.json['failed_num'] = len(self.json.get('failures', []))
        self.json['failures'] = ', '.join(self.json.get('failures', []))

        try:

            if self.json['status'] == 'failed':
                logger.warn('Failed to archive {id} because {reasons}.'.format(**self.json))
            elif self.json['status'] == 'success':
                logger.info('Successfully archived {id} with {failed_num} expected failures. ({failures})'.format(**self.json))
            else:
                logger.warning('Unknown status from %s. Dumping JSON to debug...' % self.request.remote_ip)
                logger.debug(json.dumps(self.json, indent=4, sort_keys=True))

        except KeyError:
            logger.warning('Malformed JSON from  %s. Dumping JSON to debug...' % self.request.remote_ip)
            logger.debug(json.dumps(self.json, indent=4, sort_keys=True))
            raise HTTPError(http.BAD_REQUEST)

    def post(self):
        logger.info('New Archival request from %s' % self.request.remote_ip)

        if settings.REQUIRE_SIGNED_SUBMITIONS and not signing.verify_submition(self.json):
            raise HTTPError(http.UNAUTHORIZED)

        if settings.DUMP_INCOMING_JSON:
            logger.debug('Dumping raw JSON to debug...')
            logger.debug(json.dumps(self.json, indent=4, sort_keys=True))

        container = Container.from_json(self.json)

        # Container should always be defined otherwise a
        # validation error will be raised by from_json
        if container.id in store.list_containers():
            raise HTTPError(http.BAD_REQUEST, reason='Container ID already exists')

        resp = push_task(container)
        self.set_status(resp['status'])
        self.write(resp['response'])


class ContainerHandler(BaseAPIHandler):
    URL = r'archives/containers/(.+?)/?'

    @coroutine
    def get(self, cid):
        service = self.get_query_argument('service', default=False)

        if service:
            url_or_gen, headers = store.get_container_service(cid, service)
        else:
            url_or_gen, headers = store.get_container(cid)

        if isinstance(url_or_gen, basestring):
            self.redirect(url_or_gen)
            self.finish()
        else:
            for chunk in url_or_gen:
                self.write(chunk)
                yield gen.Task(self.flush)
            self.finish()



class FileHandler(BaseAPIHandler):
    URL = r'archives/files/(.+?)/?'

    @coroutine
    def get(fid):
        try:
            self.get_query_argument('metadata')
            path = os.path.join(settings.FILES_DIR, fid)
            name = self.get_query_argument('name', default=None)
            url_or_gen, headers = store.get_file(path, name=name)
        except:
            path = os.path.join(settings.METADATA_DIR, '{}.json'.format(fid))
            url_or_gen, headers = store.get_file(path)

        for header, value in headers.items():
            self.set_header(header, value)

        if isinstance(url_or_gen, basestring):
            self.redirect(url_or_gen)
            self.finish()
        else:
            for chunk in url_or_gen:
                self.write(chunk)
                yield gen.Task(self.flush)
            self.finish()
