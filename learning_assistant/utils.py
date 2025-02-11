"""
Utils file for learning-assistant.
"""
import json
import logging

import requests
from django.conf import settings
from requests.exceptions import ConnectTimeout
from rest_framework import status as http_status

log = logging.getLogger(__name__)


def _estimated_message_tokens(message):
    """
    Estimates how many tokens are in a given message.
    """
    chars_per_token = 3.5
    json_padding = 8

    return int((len(message) - message.count(' ')) / chars_per_token) + json_padding


def get_reduced_message_list(system_list, message_list):
    """
    If messages are larger than allotted token amount, return a smaller list of messages.
    """
    total_system_tokens = sum(_estimated_message_tokens(system_message['content']) for system_message in system_list)

    max_tokens = getattr(settings, 'CHAT_COMPLETION_MAX_TOKENS', 16385)
    response_tokens = getattr(settings, 'CHAT_COMPLETION_RESPONSE_TOKENS', 1000)
    remaining_tokens = max_tokens - response_tokens - total_system_tokens

    new_message_list = []
    total_message_tokens = 0

    while total_message_tokens < remaining_tokens and len(message_list) != 0:
        new_message = message_list.pop()
        total_message_tokens += _estimated_message_tokens(new_message['content'])
        if total_message_tokens >= remaining_tokens:
            break

        # insert message at beginning of list, because we are traversing the message list from most recent to oldest
        new_message_list.insert(0, new_message)

    return new_message_list


def get_chat_response(system_list, message_list):
    """
    Pass message list to chat endpoint, as defined by the CHAT_COMPLETION_API setting.
    """
    completion_endpoint = getattr(settings, 'CHAT_COMPLETION_API', None)
    completion_endpoint_key = getattr(settings, 'CHAT_COMPLETION_API_KEY', None)
    if completion_endpoint and completion_endpoint_key:
        headers = {'Content-Type': 'application/json', 'Authorization': f"Bearer {completion_endpoint_key}"}
        connect_timeout = getattr(settings, 'CHAT_COMPLETION_API_CONNECT_TIMEOUT', 1)
        read_timeout = getattr(settings, 'CHAT_COMPLETION_API_READ_TIMEOUT', 15)

        reduced_messages = get_reduced_message_list(system_list, message_list)
        body = {"model": "gpt-3.5-turbo",
                'messages': system_list + reduced_messages,
                "temperature": 0.7}

        try:
            response = requests.post(
                completion_endpoint,
                headers=headers,
                data=json.dumps(body),
                timeout=(connect_timeout, read_timeout)
            )
            chat = response.json()
            response_status = response.status_code
        except (ConnectTimeout, ConnectionError) as e:
            error_message = str(e)
            connection_message = 'Failed to connect to chat completion API.'
            log.error(
                '%(connection_message)s %(error)s',
                {'connection_message': connection_message, 'error': error_message}
            )
            chat = connection_message
            response_status = http_status.HTTP_502_BAD_GATEWAY
    else:
        response_status = http_status.HTTP_404_NOT_FOUND
        chat = 'Completion endpoint is not defined.'

    return response_status, chat['choices'][0]['message']
