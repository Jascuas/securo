"""The catalog and the one rule it lives by: a line owns its values.

Products fill lines; they never own them. So the tests below care most
about what happens at the edges: a product renamed, archived or deleted
after an invoice named it, a term written before a product went away,
and an id that belongs to somebody else's workspace.
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice
from app.models.product import Product
from app.models.workspace import WorkspaceMember
from app.services import invoice_schedule_service as schedules
from app.services import invoice_service
from app.services import product_service as svc
from app.services.invoice_service import InvoiceError

TODAY = date(2026, 9, 23)


@pytest_asyncio.fixture
async def business_ws(client: AsyncClient, auth_headers) -> dict:
    resp = await client.post(
        "/api/workspaces",
        headers=auth_headers,
        json={"name": "Estudio", "kind": "business", "self_membership": True},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def ws_id(business_ws) -> uuid.UUID:
    return uuid.UUID(business_ws["id"])


@pytest_asyncio.fixture
async def biz_headers(auth_headers, business_ws) -> dict:
    return {**auth_headers, "X-Workspace-Id": business_ws["id"]}


async def make_product(session, ws_id, user_id, **overrides) -> Product:
    data = {
        "name": "Consulting hour",
        "unit": "h",
        "prices": [{"currency": "USD", "unit_price": "200.00"}],
    }
    data.update(overrides)
    product = await svc.create_product(session, ws_id, user_id, data)
    await session.commit()
    return product


# ---------------------------------------------------------------------------
# The catalog itself
# ---------------------------------------------------------------------------
class TestCatalog:
    @pytest.mark.asyncio
    async def test_a_product_is_created_with_its_prices(self, session, ws_id, test_user):
        p = await make_product(
            session, ws_id, test_user.id,
            prices=[
                {"currency": "USD", "unit_price": "200.00", "tax_rate": "10"},
                {"currency": "eur", "unit_price": "180.00", "billing": "recurring", "interval": "monthly", "nickname": "Monthly"},
            ],
        )
        assert p.kind == "service" and p.active
        assert [(x.currency, x.unit_price, x.billing, x.interval) for x in p.prices] == [
            ("USD", Decimal("200.00"), "one_time", None),
            ("EUR", Decimal("180.00"), "recurring", "monthly"),
        ]

    @pytest.mark.asyncio
    async def test_a_recurring_price_needs_a_cadence_and_a_one_time_price_drops_it(self, session, ws_id, test_user):
        with pytest.raises(InvoiceError) as exc:
            await make_product(session, ws_id, test_user.id, prices=[{"currency": "USD", "unit_price": "1", "billing": "recurring"}])
        assert exc.value.code == "interval_required"
        p = await make_product(session, ws_id, test_user.id, prices=[{"currency": "USD", "unit_price": "1", "billing": "one_time", "interval": "monthly"}])
        assert p.prices[0].interval is None

    @pytest.mark.asyncio
    async def test_prices_are_validated(self, session, ws_id, test_user):
        p = await make_product(session, ws_id, test_user.id)
        for bad, code in (
            ({"unit_price": "1"}, "currency_required"),
            ({"currency": "USD"}, "unit_price_required"),
            ({"currency": "USD", "unit_price": "-1"}, "negative_price"),
            ({"currency": "USD", "unit_price": "1", "billing": "weird"}, "invalid_billing"),
        ):
            with pytest.raises(InvoiceError) as exc:
                await svc.add_price(session, p, bad)
            assert exc.value.code == code

    @pytest.mark.asyncio
    async def test_imported_rows_converge_on_their_external_id(self, session, ws_id, test_user):
        with pytest.raises(InvoiceError) as exc:
            await make_product(session, ws_id, test_user.id, origin="imported")
        assert exc.value.code == "external_source_required"
        p = await make_product(
            session, ws_id, test_user.id, origin="imported", external_source="stripe", external_id="prod_1",
            prices=[{"currency": "USD", "unit_price": "10", "external_source": "stripe", "external_id": "price_1"}],
        )
        found = await svc.find_by_external_id(session, ws_id, "stripe", "prod_1")
        assert found is not None and found.id == p.id
        with pytest.raises(InvoiceError) as exc:
            await make_product(session, ws_id, test_user.id, origin="imported", external_source="stripe", external_id="prod_1", prices=[])
        assert exc.value.code == "already_imported" and exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_list_defaults_to_live_products_and_searches_by_name(self, session, ws_id, test_user):
        a = await make_product(session, ws_id, test_user.id, name="Zeta hosting", description="servers")
        b = await make_product(session, ws_id, test_user.id, name="Alpha design")
        await svc.update_product(session, b, {"active": False})
        await session.commit()
        assert [p.id for p in await svc.list_products(session, ws_id)] == [a.id]
        assert {p.id for p in await svc.list_products(session, ws_id, active=None)} == {a.id, b.id}
        assert [p.id for p in await svc.list_products(session, ws_id, active=None, q="alpha")] == [b.id]
        assert [p.id for p in await svc.list_products(session, ws_id, q="SERVERS")] == [a.id]

    @pytest.mark.asyncio
    async def test_price_for_prefers_a_live_one_time_price_in_the_currency(self, session, ws_id, test_user):
        p = await make_product(
            session, ws_id, test_user.id,
            prices=[
                {"currency": "USD", "unit_price": "1", "billing": "recurring", "interval": "monthly"},
                {"currency": "USD", "unit_price": "2"},
                {"currency": "EUR", "unit_price": "3"},
            ],
        )
        def amount(currency: str) -> Decimal | None:
            price = svc.price_for(p, currency)
            return price.unit_price if price else None

        assert amount("usd") == Decimal("2.00")
        assert amount("EUR") == Decimal("3.00")
        assert amount("BRL") is None
        await svc.update_price(session, p, p.prices[1], {"active": False})
        assert amount("USD") == Decimal("1.00")


# ---------------------------------------------------------------------------
# The bridge to invoice lines
# ---------------------------------------------------------------------------
async def an_invoice(session, ws_id, user_id, lines) -> Invoice:
    invoice = await invoice_service.create_invoice(
        session, ws_id, user_id,
        {"issue_date": TODAY, "due_date": date(2026, 10, 8), "currency": "USD", "lines": lines},
    )
    await session.commit()
    return invoice


class TestLines:
    @pytest.mark.asyncio
    async def test_a_line_remembers_its_product_and_keeps_its_own_values(self, session, ws_id, test_user):
        p = await make_product(session, ws_id, test_user.id)
        price = p.prices[0]
        inv = await an_invoice(session, ws_id, test_user.id, [
            {"description": "Consulting hour", "quantity": 3, "unit": "h", "unit_price": "180.00",
             "product_id": p.id, "price_id": price.id},
            {"description": "Travel", "unit_price": "50.00"},
        ])
        catalog, free = inv.lines
        assert catalog.product_id == p.id and catalog.price_id == price.id
        assert catalog.unit_price == Decimal("180.00")  # the typed value, not the catalog's 200
        assert free.product_id is None and free.price_id is None
        assert inv.total == Decimal("590.00")

        # Renaming and archiving the product changes nothing on the line.
        await svc.update_product(session, p, {"name": "Senior hour", "active": False})
        await session.commit()
        await session.refresh(catalog)
        assert catalog.description == "Consulting hour" and catalog.product_id == p.id

    @pytest.mark.asyncio
    async def test_a_price_alone_names_its_product(self, session, ws_id, test_user):
        p = await make_product(session, ws_id, test_user.id)
        inv = await an_invoice(session, ws_id, test_user.id, [
            {"description": "x", "unit_price": "1", "price_id": p.prices[0].id},
        ])
        assert inv.lines[0].product_id == p.id

    @pytest.mark.asyncio
    async def test_ids_from_another_workspace_or_another_product_are_refused(self, session, ws_id, test_user, client, auth_headers):
        resp = await client.post(
            "/api/workspaces", headers=auth_headers,
            json={"name": "Outra", "kind": "business", "self_membership": True},
        )
        other_ws = uuid.UUID(resp.json()["id"])
        foreign = await make_product(session, other_ws, test_user.id)
        mine = await make_product(session, ws_id, test_user.id)

        with pytest.raises(InvoiceError) as exc:
            await an_invoice(session, ws_id, test_user.id, [{"description": "x", "unit_price": "1", "product_id": foreign.id}])
        assert exc.value.code == "product_not_found"
        with pytest.raises(InvoiceError) as exc:
            await an_invoice(session, ws_id, test_user.id, [{"description": "x", "unit_price": "1", "product_id": mine.id, "price_id": foreign.prices[0].id}])
        assert exc.value.code == "price_not_found"
        with pytest.raises(InvoiceError) as exc:
            await an_invoice(session, ws_id, test_user.id, [{"description": "x", "unit_price": "1", "product_id": uuid.uuid4()}])
        assert exc.value.code == "product_not_found"

    @pytest.mark.asyncio
    async def test_a_named_product_is_archived_not_deleted(self, session, ws_id, test_user):
        p = await make_product(session, ws_id, test_user.id)
        price = p.prices[0]
        await an_invoice(session, ws_id, test_user.id, [{"description": "x", "unit_price": "1", "product_id": p.id, "price_id": price.id}])
        with pytest.raises(InvoiceError) as exc:
            await svc.delete_product(session, p)
        assert exc.value.code == "product_in_use"
        with pytest.raises(InvoiceError) as exc:
            await svc.delete_price(session, p, price)
        assert exc.value.code == "price_in_use"
        assert (await svc.usage_counts(session, ws_id, [p.id]))[p.id] == 1

        unused = await make_product(session, ws_id, test_user.id, name="Unused")
        await svc.delete_price(session, unused, unused.prices[0])
        await svc.delete_product(session, unused)
        assert await svc.get_product(session, unused.id, ws_id) is None


# ---------------------------------------------------------------------------
# Recurring agreements
# ---------------------------------------------------------------------------
class TestSchedules:
    @pytest.mark.asyncio
    async def test_a_term_carries_the_product_into_every_period(self, session, ws_id, test_user):
        p = await make_product(session, ws_id, test_user.id)
        s = await schedules.create_schedule(
            session, ws_id, test_user.id,
            {"name": "Retainer", "frequency": "monthly", "start_date": date(2026, 10, 5), "currency": "USD",
             "lines": [{"description": "Consulting hour", "quantity": 10, "unit_price": "200", "product_id": p.id, "price_id": p.prices[0].id}]},
            today=TODAY,
        )
        await session.commit()
        assert s.terms[0].lines[0]["product_id"] == str(p.id)
        [inv] = await schedules.generate_due(session, s, today=date(2026, 10, 5))
        assert inv.lines[0].product_id == p.id and inv.lines[0].price_id == p.prices[0].id

    @pytest.mark.asyncio
    async def test_a_product_deleted_after_the_term_does_not_stop_the_agreement(self, session, ws_id, test_user):
        p = await make_product(session, ws_id, test_user.id)
        s = await schedules.create_schedule(
            session, ws_id, test_user.id,
            {"name": "Retainer", "frequency": "monthly", "start_date": date(2026, 10, 5), "currency": "USD",
             "lines": [{"description": "Hour", "unit_price": "200", "product_id": p.id}]},
            today=TODAY,
        )
        await session.commit()
        await session.delete(p)
        await session.commit()
        [inv] = await schedules.generate_due(session, s, today=date(2026, 10, 5))
        assert inv.lines[0].product_id is None and inv.total == Decimal("200.00")

    @pytest.mark.asyncio
    async def test_make_recurring_keeps_the_provenance(self, session, ws_id, test_user):
        p = await make_product(session, ws_id, test_user.id)
        inv = await an_invoice(session, ws_id, test_user.id, [{"description": "Hour", "unit_price": "200", "product_id": p.id}])
        s = await schedules.make_recurring(session, inv, test_user.id, {"frequency": "monthly", "name": "R"}, today=TODAY)
        assert s.terms[0].lines[0]["product_id"] == str(p.id)


# ---------------------------------------------------------------------------
# Over HTTP
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def personal_headers(session: AsyncSession, auth_headers, test_user) -> dict:
    from app.models.workspace import Workspace

    result = await session.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == test_user.id, Workspace.kind == "personal")
        .limit(1)
    )
    return {**auth_headers, "X-Workspace-Id": str(result.scalar_one().id)}


@pytest_asyncio.fixture
async def viewer_headers(session: AsyncSession, client: AsyncClient, business_ws) -> dict:
    import bcrypt

    from app.models.user import User

    user = User(
        id=uuid.uuid4(),
        email="viewer-products@example.com",
        hashed_password=bcrypt.hashpw(b"viewerpass123", bcrypt.gensalt()).decode(),
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=uuid.UUID(business_ws["id"]), user_id=user.id, role="viewer"))
    await session.commit()
    resp = await client.post(
        "/api/auth/login",
        data={"username": "viewer-products@example.com", "password": "viewerpass123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}", "X-Workspace-Id": business_ws["id"]}


PAYLOAD = {"name": "Consulting hour", "unit": "h", "prices": [{"currency": "USD", "unit_price": "200.00"}]}


@pytest.mark.asyncio
async def test_personal_workspace_cannot_reach_the_catalog(client: AsyncClient, personal_headers):
    fake = str(uuid.uuid4())
    routes = [
        ("get", "/api/products", None),
        ("post", "/api/products", PAYLOAD),
        ("get", f"/api/products/{fake}", None),
        ("patch", f"/api/products/{fake}", {"name": "x"}),
        ("delete", f"/api/products/{fake}", None),
        ("post", f"/api/products/{fake}/prices", {"currency": "USD", "unit_price": "1"}),
        ("patch", f"/api/products/{fake}/prices/{fake}", {"active": False}),
        ("delete", f"/api/products/{fake}/prices/{fake}", None),
    ]
    for method, url, body in routes:
        resp = await getattr(client, method)(url, headers=personal_headers, **({"json": body} if body else {}))
        assert resp.status_code == 404, f"{method.upper()} {url} -> {resp.status_code}"


@pytest.mark.asyncio
async def test_viewer_reads_and_never_writes(client: AsyncClient, biz_headers, viewer_headers):
    created = (await client.post("/api/products", headers=biz_headers, json=PAYLOAD)).json()
    pid, price_id = created["id"], created["prices"][0]["id"]
    assert (await client.get("/api/products", headers=viewer_headers)).status_code == 200
    assert (await client.get(f"/api/products/{pid}", headers=viewer_headers)).status_code == 200
    writes = [
        ("post", "/api/products", PAYLOAD),
        ("patch", f"/api/products/{pid}", {"name": "x"}),
        ("delete", f"/api/products/{pid}", None),
        ("post", f"/api/products/{pid}/prices", {"currency": "EUR", "unit_price": "1"}),
        ("patch", f"/api/products/{pid}/prices/{price_id}", {"active": False}),
        ("delete", f"/api/products/{pid}/prices/{price_id}", None),
    ]
    for method, url, body in writes:
        resp = await getattr(client, method)(url, headers=viewer_headers, **({"json": body} if body else {}))
        assert resp.status_code == 403, f"{method.upper()} {url} -> {resp.status_code}"


@pytest.mark.asyncio
async def test_catalog_journey_over_http(client: AsyncClient, biz_headers, auth_headers):
    resp = await client.post("/api/products", headers=biz_headers, json=PAYLOAD)
    assert resp.status_code == 201, resp.text
    product = resp.json()
    assert product["kind"] == "service" and product["active"] and product["invoice_count"] == 0
    assert product["prices"][0]["unit_price"] == "200.00"
    pid = product["id"]

    # A second price, then a bad one.
    resp = await client.post(f"/api/products/{pid}/prices", headers=biz_headers, json={"currency": "EUR", "unit_price": "180", "billing": "recurring", "interval": "monthly"})
    assert resp.status_code == 201 and len(resp.json()["prices"]) == 2
    resp = await client.post(f"/api/products/{pid}/prices", headers=biz_headers, json={"currency": "EUR", "unit_price": "1", "billing": "recurring"})
    assert resp.status_code == 400 and resp.json()["detail"]["code"] == "interval_required"

    # An invoice from the catalog counts on the product and refuses deletion.
    resp = await client.post(
        "/api/invoices", headers=biz_headers,
        json={"currency": "USD", "lines": [{"description": "Consulting hour", "quantity": 2, "unit_price": "200.00", "product_id": pid, "price_id": product["prices"][0]["id"]}]},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["lines"][0]["product_id"] == pid
    assert (await client.get(f"/api/products/{pid}", headers=biz_headers)).json()["invoice_count"] == 1
    resp = await client.delete(f"/api/products/{pid}", headers=biz_headers)
    assert resp.status_code == 400 and resp.json()["detail"]["code"] == "product_in_use"

    # Archived: gone from the default list, back with active=false.
    resp = await client.patch(f"/api/products/{pid}", headers=biz_headers, json={"active": False})
    assert resp.status_code == 200 and resp.json()["active"] is False
    assert (await client.get("/api/products", headers=biz_headers)).json() == []
    assert [p["id"] for p in (await client.get("/api/products", headers=biz_headers, params={"active": "false"})).json()] == [pid]

    # Another workspace never sees it.
    other = await client.post("/api/workspaces", headers=auth_headers, json={"name": "Outra", "kind": "business", "self_membership": True})
    other_headers = {**auth_headers, "X-Workspace-Id": other.json()["id"]}
    assert (await client.get(f"/api/products/{pid}", headers=other_headers)).status_code == 404
    resp = await client.post("/api/invoices", headers=other_headers, json={"currency": "USD", "lines": [{"description": "x", "unit_price": "1", "product_id": pid}]})
    assert resp.status_code == 404 and resp.json()["detail"]["code"] == "product_not_found"

    # Unused products simply go.
    resp = await client.post("/api/products", headers=biz_headers, json={"name": "Nothing yet"})
    assert (await client.delete(f"/api/products/{resp.json()['id']}", headers=biz_headers)).status_code == 204
