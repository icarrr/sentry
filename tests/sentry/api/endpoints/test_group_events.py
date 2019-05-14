from __future__ import absolute_import

import six

from datetime import timedelta
from django.utils import timezone
from freezegun import freeze_time
from mock import patch
from rest_framework.response import Response

from sentry import options
from sentry.models import Environment
from sentry.testutils import (
    APITestCase,
    SnubaTestCase,
)


class GroupEventsTest(APITestCase, SnubaTestCase):
    def setUp(self):
        super(GroupEventsTest, self).setUp()
        options.set('snuba.events-queries.enabled', False)

    def test_simple(self):
        self.login_as(user=self.user)

        group = self.create_group()
        event_1 = self.create_event(event_id='a' * 32, group=group)
        event_2 = self.create_event(event_id='b' * 32, group=group)

        url = u'/api/0/issues/{}/events/'.format(group.id)
        response = self.client.get(url, format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 2
        assert sorted(map(lambda x: x['id'], response.data)) == sorted(
            [
                six.text_type(event_1.id),
                six.text_type(event_2.id),
            ]
        )

    def test_tags(self):
        self.login_as(user=self.user)

        event_1 = self.store_event(
            data={
                'fingerprint': ['put-me-in-group1'],
                'environment': self.environment.name,
                'timestamp': (timezone.now() - timedelta(minutes=5)).isoformat()[:19],
                'tags': {
                    'foo': 'baz',
                    'bar': 'buz',
                },

            },
            project_id=self.project.id,
        )
        event_2 = self.store_event(
            data={
                'fingerprint': ['put-me-in-group1'],
                'environment': self.environment.name,
                'timestamp': (timezone.now() - timedelta(minutes=5)).isoformat()[:19],
                'tags': {
                    'bar': 'biz',
                },

            },
            project_id=self.project.id,
        )

        group = event_1.group

        url = u'/api/0/issues/{}/events/'.format(group.id)
        response = self.client.get(url + '?query=foo:baz', format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 1
        assert response.data[0]['id'] == six.text_type(event_1.id)

        response = self.client.get(url + '?query=bar:biz', format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 1
        assert response.data[0]['id'] == six.text_type(event_2.id)

        response = self.client.get(url + '?query=bar:biz%20foo:baz', format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 0

        response = self.client.get(url + '?query=bar:buz%20foo:baz', format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 1
        assert response.data[0]['id'] == six.text_type(event_1.id)

        response = self.client.get(url + '?query=bar:baz', format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 0

        response = self.client.get(url + '?query=a:b', format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 0

        response = self.client.get(url + '?query=bar:b', format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 0

        response = self.client.get(url + '?query=bar:baz', format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 0

    def test_search_event_by_id(self):
        self.login_as(user=self.user)

        group = self.create_group()
        event_1 = self.create_event(event_id='a' * 32, group=group)
        self.create_event(event_id='b' * 32, group=group)
        query = event_1.event_id

        url = u'/api/0/issues/{}/events/?query={}'.format(group.id, query)
        response = self.client.get(url, format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 1
        assert response.data[0]['eventID'] == event_1.event_id

    def test_search_event_by_message(self):
        self.login_as(user=self.user)

        group = self.create_group()
        event_1 = self.create_event(event_id='a' * 32, group=group, message="foo bar hello world")

        event_2 = self.create_event(event_id='b' * 32, group=group, message='this bar hello world ')

        query_1 = "foo"
        query_2 = "hello+world"

        # Single Word Query
        url = u'/api/0/issues/{}/events/?query={}'.format(group.id, query_1)
        response = self.client.get(url, format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 1
        assert response.data[0]['id'] == six.text_type(
            event_1.id) and response.data[0]['eventID'] == event_1.event_id

        # Multiple Word Query
        url = u'/api/0/issues/{}/events/?query={}'.format(group.id, query_2)
        response = self.client.get(url, format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 2
        assert sorted(map(lambda x: x['id'], response.data)) == sorted(
            [
                six.text_type(event_1.id),
                six.text_type(event_2.id),
            ]
        )

    def test_environment(self):
        self.login_as(user=self.user)
        events = {}

        for name in ['production', 'development']:
            environment = Environment.get_or_create(self.project, name)
            events[name] = event = self.store_event(
                data={
                    'fingerprint': ['put-me-in-group1'],
                    'environment': environment.name,
                    'timestamp': (timezone.now() - timedelta(minutes=5)).isoformat()[:19],
                    'tags': {
                        'foo': 'baz',
                        'bar': 'buz',
                    },

                },
                project_id=self.project.id,
            )
        group = event.group
        url = u'/api/0/issues/{}/events/'.format(group.id)
        response = self.client.get(url + '?environment=production', format='json')

        assert response.status_code == 200, response.content
        assert set(map(lambda x: x['id'], response.data)) == set([
            six.text_type(events['production'].id),
        ])

        url = u'/api/0/issues/{}/events/'.format(group.id)
        response = self.client.get(url + '?environment=invalid', format='json')

        assert response.status_code == 200, response.content
        assert response.data == []

        url = u'/api/0/issues/{}/events/'.format(group.id)
        response = self.client.get(
            url + '?environment=production&query=environment:development',
            format='json')

        assert response.status_code == 200, response.content
        assert response.data == []

    def test_filters_based_on_retention(self):
        self.login_as(user=self.user)

        project = self.create_project()
        group = self.create_group(project=project)
        self.create_event(
            event_id='a' * 32,
            group=group,
            datetime=timezone.now() - timedelta(days=2),
        )
        event_2 = self.create_event(event_id='b' * 32, group=group)

        with self.options({'system.event-retention-days': 1}):
            response = self.client.get(u'/api/0/issues/{}/events/'.format(group.id))

        assert response.status_code == 200, response.content
        assert len(response.data) == 1
        assert sorted(map(lambda x: x['id'], response.data)) == sorted(
            [
                six.text_type(event_2.id),
            ]
        )

    @freeze_time()
    def test_date_filters(self):
        self.login_as(user=self.user)

        project = self.create_project()
        group = self.create_group(project=project)
        event_1 = self.create_event(
            event_id='a' * 32,
            group=group,
            datetime=timezone.now() - timedelta(days=2),
        )
        event_2 = self.create_event(event_id='b' * 32, group=group)

        response = self.client.get(
            u'/api/0/issues/{}/events/'.format(group.id),
            data={
                'statsPeriod': '3d',
            },
        )

        assert response.status_code == 200, response.content
        assert len(response.data) == 2
        assert sorted(map(lambda x: x['id'], response.data)) == sorted(
            [
                six.text_type(event_1.id),
                six.text_type(event_2.id),
            ]
        )

        response = self.client.get(
            u'/api/0/issues/{}/events/'.format(group.id),
            data={
                'statsPeriod': '1d',
            },
        )

        assert response.status_code == 200, response.content
        assert len(response.data) == 1
        assert response.data[0]['id'] == six.text_type(event_2.id)

    def test_force_snuba(self):
        self.login_as(user=self.user)
        project = self.create_project()
        group = self.create_group(project=project)
        with patch('sentry.api.endpoints.group_events.GroupEventsEndpoint._get_events_snuba') as get_events_snuba:
            get_events_snuba.return_value = Response([])
            self.client.get(
                u'/api/0/issues/{}/events/'.format(group.id),
                data={
                    'statsPeriod': '3d',
                    'enable_snuba': '1',
                },
            )
            assert get_events_snuba.call_count == 1
