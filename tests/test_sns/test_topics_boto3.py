from __future__ import unicode_literals
import boto3
import six
import json

import sure  # noqa

from botocore.exceptions import ClientError
from moto import mock_sns
from moto.sns.models import DEFAULT_TOPIC_POLICY, DEFAULT_EFFECTIVE_DELIVERY_POLICY, DEFAULT_PAGE_SIZE


@mock_sns
def test_create_and_delete_topic():
    conn = boto3.client("sns", region_name="us-east-1")
    for topic_name in ('some-topic', '-some-topic-', '_some-topic_', 'a' * 256):
        conn.create_topic(Name=topic_name)

        topics_json = conn.list_topics()
        topics = topics_json["Topics"]
        topics.should.have.length_of(1)
        topics[0]['TopicArn'].should.equal(
            "arn:aws:sns:{0}:123456789012:{1}"
            .format(conn._client_config.region_name, topic_name)
        )

        # Delete the topic
        conn.delete_topic(TopicArn=topics[0]['TopicArn'])

        # And there should now be 0 topics
        topics_json = conn.list_topics()
        topics = topics_json["Topics"]
        topics.should.have.length_of(0)


@mock_sns
def test_create_topic_with_attributes():
    conn = boto3.client("sns", region_name="us-east-1")
    conn.create_topic(Name='some-topic-with-attribute', Attributes={'DisplayName': 'test-topic'})
    topics_json = conn.list_topics()
    topic_arn = topics_json["Topics"][0]['TopicArn']

    attributes = conn.get_topic_attributes(TopicArn=topic_arn)['Attributes']
    attributes['DisplayName'].should.equal('test-topic')


@mock_sns
def test_create_topic_with_tags():
    conn = boto3.client("sns", region_name="us-east-1")
    response = conn.create_topic(
        Name='some-topic-with-tags',
        Tags=[
            {
                'Key': 'tag_key_1',
                'Value': 'tag_value_1'
            },
            {
                'Key': 'tag_key_2',
                'Value': 'tag_value_2'
            }
        ]
    )
    topic_arn = response['TopicArn']

    conn.list_tags_for_resource(ResourceArn=topic_arn)['Tags'].should.equal([
        {
            'Key': 'tag_key_1',
            'Value': 'tag_value_1'
        },
        {
            'Key': 'tag_key_2',
            'Value': 'tag_value_2'
        }
    ])


@mock_sns
def test_create_topic_should_be_indempodent():
    conn = boto3.client("sns", region_name="us-east-1")
    topic_arn = conn.create_topic(Name="some-topic")['TopicArn']
    conn.set_topic_attributes(
        TopicArn=topic_arn,
        AttributeName="DisplayName",
        AttributeValue="should_be_set"
    )
    topic_display_name = conn.get_topic_attributes(
        TopicArn=topic_arn
    )['Attributes']['DisplayName']
    topic_display_name.should.be.equal("should_be_set")

    #recreate topic to prove indempodentcy
    topic_arn = conn.create_topic(Name="some-topic")['TopicArn']
    topic_display_name = conn.get_topic_attributes(
        TopicArn=topic_arn
    )['Attributes']['DisplayName']
    topic_display_name.should.be.equal("should_be_set")

@mock_sns
def test_get_missing_topic():
    conn = boto3.client("sns", region_name="us-east-1")
    conn.get_topic_attributes.when.called_with(
        TopicArn="a-fake-arn").should.throw(ClientError)

@mock_sns
def test_create_topic_must_meet_constraints():
    conn = boto3.client("sns", region_name="us-east-1")
    common_random_chars = [':', ";", "!", "@", "|", "^", "%"]
    for char in common_random_chars:
        conn.create_topic.when.called_with(
            Name="no%s_invalidchar" % char).should.throw(ClientError)
    conn.create_topic.when.called_with(
            Name="no spaces allowed").should.throw(ClientError)


@mock_sns
def test_create_topic_should_be_of_certain_length():
    conn = boto3.client("sns", region_name="us-east-1")
    too_short = ""
    conn.create_topic.when.called_with(
            Name=too_short).should.throw(ClientError)
    too_long = "x" * 257
    conn.create_topic.when.called_with(
            Name=too_long).should.throw(ClientError)


@mock_sns
def test_create_topic_in_multiple_regions():
    for region in ['us-west-1', 'us-west-2']:
        conn = boto3.client("sns", region_name=region)
        conn.create_topic(Name="some-topic")
        list(conn.list_topics()["Topics"]).should.have.length_of(1)


@mock_sns
def test_topic_corresponds_to_region():
    for region in ['us-east-1', 'us-west-2']:
        conn = boto3.client("sns", region_name=region)
        conn.create_topic(Name="some-topic")
        topics_json = conn.list_topics()
        topic_arn = topics_json["Topics"][0]['TopicArn']
        topic_arn.should.equal(
            "arn:aws:sns:{0}:123456789012:some-topic".format(region))


@mock_sns
def test_topic_attributes():
    conn = boto3.client("sns", region_name="us-east-1")
    conn.create_topic(Name="some-topic")

    topics_json = conn.list_topics()
    topic_arn = topics_json["Topics"][0]['TopicArn']

    attributes = conn.get_topic_attributes(TopicArn=topic_arn)['Attributes']
    attributes["TopicArn"].should.equal(
        "arn:aws:sns:{0}:123456789012:some-topic"
        .format(conn._client_config.region_name)
    )
    attributes["Owner"].should.equal('123456789012')
    json.loads(attributes["Policy"]).should.equal(DEFAULT_TOPIC_POLICY)
    attributes["DisplayName"].should.equal("")
    attributes["SubscriptionsPending"].should.equal('0')
    attributes["SubscriptionsConfirmed"].should.equal('0')
    attributes["SubscriptionsDeleted"].should.equal('0')
    attributes["DeliveryPolicy"].should.equal("")
    json.loads(attributes["EffectiveDeliveryPolicy"]).should.equal(
        DEFAULT_EFFECTIVE_DELIVERY_POLICY)

    # boto can't handle prefix-mandatory strings:
    # i.e. unicode on Python 2 -- u"foobar"
    # and bytes on Python 3 -- b"foobar"
    if six.PY2:
        policy = json.dumps({b"foo": b"bar"})
        displayname = b"My display name"
        delivery = json.dumps(
            {b"http": {b"defaultHealthyRetryPolicy": {b"numRetries": 5}}})
    else:
        policy = json.dumps({u"foo": u"bar"})
        displayname = u"My display name"
        delivery = json.dumps(
            {u"http": {u"defaultHealthyRetryPolicy": {u"numRetries": 5}}})
    conn.set_topic_attributes(TopicArn=topic_arn,
                              AttributeName="Policy",
                              AttributeValue=policy)
    conn.set_topic_attributes(TopicArn=topic_arn,
                              AttributeName="DisplayName",
                              AttributeValue=displayname)
    conn.set_topic_attributes(TopicArn=topic_arn,
                              AttributeName="DeliveryPolicy",
                              AttributeValue=delivery)

    attributes = conn.get_topic_attributes(TopicArn=topic_arn)['Attributes']
    attributes["Policy"].should.equal('{"foo": "bar"}')
    attributes["DisplayName"].should.equal("My display name")
    attributes["DeliveryPolicy"].should.equal(
        '{"http": {"defaultHealthyRetryPolicy": {"numRetries": 5}}}')


@mock_sns
def test_topic_paging():
    conn = boto3.client("sns", region_name="us-east-1")
    for index in range(DEFAULT_PAGE_SIZE + int(DEFAULT_PAGE_SIZE / 2)):
        conn.create_topic(Name="some-topic_" + str(index))

    response = conn.list_topics()
    topics_list = response["Topics"]
    next_token = response["NextToken"]

    len(topics_list).should.equal(DEFAULT_PAGE_SIZE)
    int(next_token).should.equal(DEFAULT_PAGE_SIZE)

    response = conn.list_topics(NextToken=next_token)
    topics_list = response["Topics"]
    response.shouldnt.have("NextToken")

    topics_list.should.have.length_of(int(DEFAULT_PAGE_SIZE / 2))


@mock_sns
def test_add_remove_permissions():
    conn = boto3.client('sns', region_name='us-east-1')
    response = conn.create_topic(Name='testpermissions')

    conn.add_permission(
        TopicArn=response['TopicArn'],
        Label='Test1234',
        AWSAccountId=['999999999999'],
        ActionName=['AddPermission']
    )
    conn.remove_permission(
        TopicArn=response['TopicArn'],
        Label='Test1234'
    )


@mock_sns
def test_tag_topic():
    conn = boto3.client('sns', region_name='us-east-1')
    response = conn.create_topic(
        Name = 'some-topic-with-tags'
    )
    topic_arn = response['TopicArn']

    conn.tag_resource(
        ResourceArn=topic_arn,
        Tags=[
            {
                'Key': 'tag_key_1',
                'Value': 'tag_value_1'
            }
        ]
    )
    conn.list_tags_for_resource(ResourceArn = topic_arn)['Tags'].should.equal([
        {
            'Key': 'tag_key_1',
            'Value': 'tag_value_1'
        }
    ])

    conn.tag_resource(
        ResourceArn=topic_arn,
        Tags=[
            {
                'Key': 'tag_key_2',
                'Value': 'tag_value_2'
            }
        ]
    )
    conn.list_tags_for_resource(ResourceArn = topic_arn)['Tags'].should.equal([
        {
            'Key': 'tag_key_1',
            'Value': 'tag_value_1'
        },
        {
            'Key': 'tag_key_2',
            'Value': 'tag_value_2'
        }
    ])

    conn.tag_resource(
        ResourceArn = topic_arn,
        Tags = [
            {
                'Key': 'tag_key_1',
                'Value': 'tag_value_X'
            }
        ]
    )
    conn.list_tags_for_resource(ResourceArn = topic_arn)['Tags'].should.equal([
        {
            'Key': 'tag_key_1',
            'Value': 'tag_value_X'
        },
        {
            'Key': 'tag_key_2',
            'Value': 'tag_value_2'
        }
    ])


@mock_sns
def test_untag_topic():
    conn = boto3.client('sns', region_name = 'us-east-1')
    response = conn.create_topic(
        Name = 'some-topic-with-tags',
        Tags = [
            {
                'Key': 'tag_key_1',
                'Value': 'tag_value_1'
            },
            {
                'Key': 'tag_key_2',
                'Value': 'tag_value_2'
            }
        ]
    )
    topic_arn = response['TopicArn']

    conn.untag_resource(
        ResourceArn = topic_arn,
        TagKeys = [
            'tag_key_1'
        ]
    )
    conn.list_tags_for_resource(ResourceArn = topic_arn)['Tags'].should.equal([
        {
            'Key': 'tag_key_2',
            'Value': 'tag_value_2'
        }
    ])

    # removing a non existing tag should not raise any error
    conn.untag_resource(
        ResourceArn = topic_arn,
        TagKeys = [
            'not-existing-tag'
        ]
    )
    conn.list_tags_for_resource(ResourceArn = topic_arn)['Tags'].should.equal([
        {
            'Key': 'tag_key_2',
            'Value': 'tag_value_2'
        }
    ])


@mock_sns
def test_list_tags_for_resource_error():
    conn = boto3.client('sns', region_name = 'us-east-1')
    conn.create_topic(
        Name = 'some-topic-with-tags',
        Tags = [
            {
                'Key': 'tag_key_1',
                'Value': 'tag_value_X'
            }
        ]
    )

    conn.list_tags_for_resource.when.called_with(
        ResourceArn = 'not-existing-topic'
    ).should.throw(
        ClientError,
        'Resource does not exist'
    )


@mock_sns
def test_tag_resource_errors():
    conn = boto3.client('sns', region_name = 'us-east-1')
    response = conn.create_topic(
        Name = 'some-topic-with-tags',
        Tags = [
            {
                'Key': 'tag_key_1',
                'Value': 'tag_value_X'
            }
        ]
    )
    topic_arn = response['TopicArn']

    conn.tag_resource.when.called_with(
        ResourceArn = 'not-existing-topic',
        Tags = [
            {
                'Key': 'tag_key_1',
                'Value': 'tag_value_1'
            }
        ]
    ).should.throw(
        ClientError,
        'Resource does not exist'
    )

    too_many_tags = [{'Key': 'tag_key_{}'.format(i), 'Value': 'tag_value_{}'.format(i)} for i in range(51)]
    conn.tag_resource.when.called_with(
        ResourceArn = topic_arn,
        Tags = too_many_tags
    ).should.throw(
        ClientError,
        'Could not complete request: tag quota of per resource exceeded'
    )

    # when the request fails, the tags should not be updated
    conn.list_tags_for_resource(ResourceArn = topic_arn)['Tags'].should.equal([
        {
            'Key': 'tag_key_1',
            'Value': 'tag_value_X'
        }
    ])


@mock_sns
def test_untag_resource_error():
    conn = boto3.client('sns', region_name = 'us-east-1')
    conn.create_topic(
        Name = 'some-topic-with-tags',
        Tags = [
            {
                'Key': 'tag_key_1',
                'Value': 'tag_value_X'
            }
        ]
    )

    conn.untag_resource.when.called_with(
        ResourceArn = 'not-existing-topic',
        TagKeys = [
            'tag_key_1'
        ]
    ).should.throw(
        ClientError,
        'Resource does not exist'
    )
