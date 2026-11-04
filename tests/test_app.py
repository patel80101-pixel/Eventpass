import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db"), "SEED_DATA": False})
    with app.test_client() as c:
        yield c


def make_event(client, capacity=10, price=100, title="Test Fest"):
    return client.post("/events/new", data={
        "title": title, "category": "Technical", "venue": "Hall A",
        "event_date": "2026-12-01", "event_time": "10:00",
        "capacity": capacity, "price": price, "description": "demo"}, follow_redirects=True)


def book(client, event_id=1, email="a@x.com", tickets=1):
    return client.post(f"/events/{event_id}/register", data={
        "name": "Asha", "email": email, "phone": "9876543210", "tickets": tickets})


def ticket_code(resp):
    return resp.headers["Location"].rsplit("/", 1)[-1]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.get_json()["status"] == "ok"


def test_pages_load(client):
    make_event(client)
    for url in ["/", "/events", "/events/new", "/events/1", "/checkin", "/api/events", "/api/stats"]:
        assert client.get(url).status_code == 200, url


def test_create_event_and_validation(client):
    assert b"Test Fest" in make_event(client).data
    bad = client.post("/events/new", data={"title": "", "category": "Nope", "venue": "",
                                           "event_date": "x", "event_time": "x", "capacity": "-1"})
    assert bad.status_code == 400
    assert len(client.get("/api/events").get_json()) == 1


def test_booking_creates_ticket_and_charges(client):
    make_event(client, price=150)
    r = book(client, tickets=2)
    assert r.status_code == 302
    code = ticket_code(r)
    assert code.startswith("EP-")
    page = client.get(f"/ticket/{code}")
    assert page.status_code == 200 and b"300" in page.data
    assert client.get("/api/stats").get_json()["tickets_sold"] == 2


def test_overbooking_blocked(client):
    make_event(client, capacity=3)
    book(client, email="a@x.com", tickets=2)
    r = book(client, email="b@x.com", tickets=2)
    assert client.get(r.headers["Location"]).status_code == 200
    assert client.get("/api/stats").get_json()["tickets_sold"] == 2


def test_duplicate_email_blocked(client):
    make_event(client)
    book(client, email="a@x.com")
    book(client, email="A@x.com")
    assert client.get("/api/stats").get_json()["tickets_sold"] == 1


def test_ticket_limit(client):
    make_event(client, capacity=50)
    book(client, tickets=6)
    assert client.get("/api/stats").get_json()["tickets_sold"] == 0


def test_cancel_releases_seats(client):
    make_event(client, capacity=2)
    code = ticket_code(book(client, tickets=2))
    client.post(f"/ticket/{code}/cancel")
    assert client.get("/api/events").get_json()[0]["available"] == 2
    assert ticket_code(book(client, email="b@x.com", tickets=2)).startswith("EP-")


def test_checkin_once_only(client):
    make_event(client)
    code = ticket_code(book(client))
    first = client.post("/checkin", data={"code": code.lower()})
    assert b"Welcome" in first.data
    second = client.post("/checkin", data={"code": code})
    assert b"already checked in" in second.data
    assert b"No ticket found" in client.post("/checkin", data={"code": "EP-NOPE00"}).data


def test_capacity_cannot_drop_below_booked(client):
    make_event(client, capacity=5)
    book(client, tickets=4)
    r = client.post("/events/1/edit", data={
        "title": "Test Fest", "category": "Technical", "venue": "Hall A", "event_date": "2026-12-01",
        "event_time": "10:00", "capacity": 3, "price": 100})
    assert r.status_code == 400


def test_delete_event_and_404(client):
    make_event(client)
    client.post("/events/1/delete")
    assert client.get("/events/1").status_code == 404
    assert client.get("/ticket/EP-NOPE00").status_code == 404
