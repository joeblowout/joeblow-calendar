# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from datetime import datetime, timedelta
from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.urls import reverse

from django.urls import path
from django.views.generic import TemplateView

from dateutil import tz, parser
from tutorial.auth_helper import (get_sign_in_flow, get_token_from_code, store_user,
    remove_user_and_token, get_token)
from tutorial.graph_helper import get_user, get_photo, get_iana_from_windows, get_calendar_events, create_event
import os

pfp_name = ''

def initialize_context(request):
    context = {}

    # Check for any errors in the session
    error = request.session.pop('flash_error', None)

    if error is not None:
        context['errors'] = []
        context['errors'].append(error)

    # Check for user in the session
    context['user'] = request.session.get('user', {'is_authenticated': False})
    return context

def home(request):
    context = initialize_context(request)

    return render(request, 'tutorial/home.html', context)

def sign_in(request):
    # Get the sign-in flow
    flow = get_sign_in_flow()
    # Save the expected flow so we can use it in the callback
    request.session['auth_flow'] = flow

    # Redirect to the Azure sign-in page
    return HttpResponseRedirect(flow['auth_uri'])

def callback(request):
    # Make the token request
    result = get_token_from_code(request)

    #Get the user's profile
    user = get_user(result['access_token'])
    user_photo, pfp_name = get_photo(result['access_token'], user)

    # Store user
    store_user(request, user, user_photo, pfp_name)
    return HttpResponseRedirect(reverse('home'))

def sign_out(request):
    # Remove profile picture
    pfp_name = request.session['user']['pfp_name']
    if os.path.exists(f"tutorial/static/tmp/{pfp_name}"):
        os.remove(f"tutorial/static/tmp/{pfp_name}")

    # Clear out the user and token
    remove_user_and_token(request)
    return HttpResponseRedirect(reverse('home'))

def calendar(request):
    context = initialize_context(request)
    user = context['user']
    if not user['is_authenticated']:
        return HttpResponseRedirect(reverse('signin'))

    # Load the user's time zone
    # Microsoft Graph can return the user's time zone as either
    # a Windows time zone name or an IANA time zone identifier
    # Python datetime requires IANA, so convert Windows to IANA
    time_zone = get_iana_from_windows(user['timeZone'])
    tz_info = tz.gettz(time_zone)

    # Get midnight today in user's time zone
    today = datetime.now(tz_info).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0)

    # Based on today, get the start of the week (Sunday)
    if today.weekday() != 6:
        start = today - timedelta(days=today.isoweekday())
    else:
        start = today

    end = start + timedelta(days=7)

    token = get_token(request)

    events = get_calendar_events(
        token,
        start.isoformat(timespec='seconds'),
        end.isoformat(timespec='seconds'),
        user['timeZone'])

    if events:
        # Convert the ISO 8601 date times to a datetime object
        # This allows the Django template to format the value nicely
        for event in events['value']:
            event['start']['dateTime'] = parser.parse(event['start']['dateTime'])
            event['end']['dateTime'] = parser.parse(event['end']['dateTime'])

        context['events'] = events['value']

    return render(request, 'tutorial/calendar.html', context)

def new_event(request):
    context = initialize_context(request)
    user = context['user']
    if not user['is_authenticated']:
        return HttpResponseRedirect(reverse('signin'))

    if request.method == 'POST':
        # Validate the form values
        # Required values
        if (not request.POST['ev-subject']) or \
            (not request.POST['ev-start']) or \
            (not request.POST['ev-end']):
            context['errors'] = [
                {
                    'message': 'Invalid values',
                    'debug': 'The subject, start and end fields can\'t be empty.'
                }
            ]
            return render(request, 'tutorial/newevent.html', context)

        attendees = None
        if request.POST['ev-attendees']:
            attendees = request.POST['ev-attendees'].split(';')

        # Create the event
        token = get_token(request)

        create_event(
          token,
          request.POST['ev-subject'],
          request.POST['ev-start'],
          request.POST['ev-end'],
          attendees,
          request.POST['ev-body'],
          user['timeZone'])

        # Redirect back to calendar view
        return HttpResponseRedirect(reverse('calendar'))
    else:
        # Render the form
        return render(request, 'tutorial/newevent.html', context)