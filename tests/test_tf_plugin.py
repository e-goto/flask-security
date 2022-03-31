"""
    test_tf_plugin
    ~~~~~~~~~~~~~~~~~

    tf_plugin tests

    :copyright: (c) 2022-2022 by J. Christopher Wagner (jwag).
    :license: MIT, see LICENSE for more details.
"""

import json
import pytest

from tests.test_utils import (
    SmsTestSender,
    get_session,
    get_existing_session,
    logout,
)
from flask_security import (
    SmsSenderFactory,
)

from tests.test_two_factor import tf_in_session
from tests.test_webauthn import HackWebauthnUtil, wan_signin, setup_tf, reg_2_keys

pytest.importorskip("webauthn")


SmsSenderFactory.senders["test"] = SmsTestSender


@pytest.mark.webauthn()
@pytest.mark.two_factor()
@pytest.mark.settings(webauthn_util_cls=HackWebauthnUtil)
def test_tf_select(app, client, get_message):
    # Test basic select mechanism when more than one 2FA has been setup
    wankeys = reg_2_keys(client)  # add a webauthn 2FA key (authenticates)
    sms_sender = setup_tf(client)
    logout(client)

    # since we have 2 2FA methods configured - we should get the tf-select form
    response = client.post(
        "/login",
        data=dict(email="matt@lp.com", password="password"),
        follow_redirects=True,
    )
    assert b"Select Two Factor Method" in response.data
    response = client.post(
        "/tf-select", data=dict(which="webauthn"), follow_redirects=True
    )
    assert b"Use Your WebAuthn Security Key as a Second Factor" in response.data

    response = wan_signin(client, "matt@lp.com", wankeys["secondary"]["signin"])
    assert not tf_in_session(get_session(response))

    # verify actually logged in
    response = client.get("/profile", follow_redirects=False)
    assert response.status_code == 200

    # now do other 2FA
    logout(client)
    response = client.post(
        "/login",
        data=dict(email="matt@lp.com", password="password"),
        follow_redirects=True,
    )
    assert b"Select Two Factor Method" in response.data
    response = client.post("/tf-select", data=dict(which="sms"), follow_redirects=True)
    assert b"Please enter your authentication code generated via: sms" in response.data
    code = sms_sender.messages[0].split()[-1]
    response = client.post("/tf-validate", data=dict(code=code), follow_redirects=True)
    assert b"Your token has been confirmed" in response.data

    assert not tf_in_session(get_session(response))

    # verify actually logged in
    response = client.get("/profile", follow_redirects=False)
    assert response.status_code == 200
    assert not tf_in_session(get_existing_session(client))


@pytest.mark.webauthn()
@pytest.mark.two_factor()
@pytest.mark.settings(webauthn_util_cls=HackWebauthnUtil)
def test_tf_select_json(app, client, get_message):
    # Test basic select mechanism when more than one 2FA has been setup
    wankeys = reg_2_keys(client)  # add a webauthn 2FA key (authenticates)
    setup_tf(client)
    logout(client)

    # since we have 2 2FA methods configured - we should get the tf-select form
    response = client.post(
        "/login", json=dict(email="matt@lp.com", password="password")
    )
    assert response.json["response"]["tf_required"]
    choices = response.json["response"]["tf_setup_methods"]
    assert all(k in choices for k in ["sms", "webauthn"])

    # use webauthn as the second factor
    response = client.post("/tf-select", json=dict(which="webauthn"))
    signin_url = response.json["response"]["tf_signin_url"]
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    response = client.post(signin_url, headers=headers)
    response_url = f'wan-signin/{response.json["response"]["wan_state"]}'
    response = client.post(
        response_url,
        json=dict(credential=json.dumps(wankeys["secondary"]["signin"])),
    )
    assert response.status_code == 200
    assert not tf_in_session(get_existing_session(client))

    response = client.get("/profile", follow_redirects=False)
    assert response.status_code == 200


@pytest.mark.two_factor()
def test_tf_select_auth(app, client, get_message):
    # /tf-select is an unauthenticated endpoint - make sure only allowable in correct
    # state.
    response = client.get("/tf-select", follow_redirects=False)
    assert "/login" in response.location