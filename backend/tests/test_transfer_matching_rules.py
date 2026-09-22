"""Transfer pairing, now that its rules are a document somebody can read.

Every test here is a report from the issue tracker or a promise the
feature makes about itself. The claim under all of them: **what the old
detector did silently, this does visibly, and the cases it got wrong it
now declines to guess at.**
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.reconciliation import ReconciliationSuggestion
from app.models.transaction import Transaction
from app.services import reconciliation_policy
from app.services import reconciliation_rule_service as rule_service
from app.services.text_similarity import names_account
from app.services.transfer_detection_service import detect_transfer_pairs

TODAY = date.today()
NODE = reconciliation_policy.MATCH_TRANSFER["node"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _account(
    session: AsyncSession, user_id, workspace_id, name: str, kind: str = "checking"
) -> Account:
    account = Account(
        id=uuid.uuid4(),
        user_id=user_id,
        workspace_id=workspace_id,
        name=name,
        type=kind,
        currency="EUR",
        balance=Decimal("0"),
    )
    session.add(account)
    await session.commit()
    return account


async def _txn(
    session: AsyncSession,
    user_id,
    workspace_id,
    account: Account,
    *,
    amount: str,
    kind: str,
    when: date,
    description: str = "Movement",
) -> Transaction:
    txn = Transaction(
        id=uuid.uuid4(),
        user_id=user_id,
        workspace_id=workspace_id,
        account_id=account.id,
        description=description,
        amount=Decimal(amount),
        currency="EUR",
        date=when,
        effective_date=when,
        type=kind,
        source="sync",
        created_at=datetime.now(timezone.utc),
    )
    session.add(txn)
    await session.commit()
    return txn


async def _pending(session: AsyncSession, workspace_id) -> list[ReconciliationSuggestion]:
    result = await session.execute(
        select(ReconciliationSuggestion).where(
            ReconciliationSuggestion.workspace_id == workspace_id,
            ReconciliationSuggestion.status == "pending",
        )
    )
    return list(result.scalars().all())


@pytest_asyncio.fixture
async def ws(test_workspace):
    return test_workspace


# ---------------------------------------------------------------------------
# The signal the old detector never had
# ---------------------------------------------------------------------------
def test_an_account_name_is_found_however_the_bank_printed_it():
    assert names_account("To FORTUNEO ACCOUNT 1234", "Fortuneo")
    assert names_account("NUBANK*IFOOD", "Nubank")
    # Accents come off both sides: the same bank prints it both ways.
    assert names_account("TED ITAU UNIBANCO", "Itaú")


def test_a_generic_account_name_names_nothing():
    """Otherwise "Conta Corrente" matches most of a Brazilian statement,
    and the signal is worse than not having it."""
    assert not names_account("PIX ENVIADO CONTA CORRENTE", "Conta Corrente")
    assert not names_account("To FORTUNEO ACCOUNT", "Trade Republic")


# ---------------------------------------------------------------------------
# #973: the wrong counterpart
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_description_decides_between_two_same_day_transfers(
    session: AsyncSession, test_user, ws
):
    """Two transfers of the same amount leave one account on one day.

    The old detector paired the incoming leg with whichever debit the
    database returned first, and left the one that named its destination
    unpaired. Nothing in the UI looked wrong; only the descriptions
    contradicted the link.
    """
    bnp = await _account(session, test_user.id, ws.id, "BNP checking")
    fortuneo = await _account(session, test_user.id, ws.id, "Fortuneo")
    await _account(session, test_user.id, ws.id, "Trade Republic")

    to_tr = await _txn(
        session, test_user.id, ws.id, bnp,
        amount="100.00", kind="debit", when=TODAY,
        description="To Trade Republic 0987",
    )
    to_fortuneo = await _txn(
        session, test_user.id, ws.id, bnp,
        amount="100.00", kind="debit", when=TODAY,
        description="To FORTUNEO ACCOUNT 1234",
    )
    arrival = await _txn(
        session, test_user.id, ws.id, fortuneo,
        amount="100.00", kind="credit", when=TODAY + timedelta(days=2),
        description="Transfer from BNP",
    )

    assert await detect_transfer_pairs(session, ws.id) == 1
    await session.commit()
    for row in (to_tr, to_fortuneo, arrival):
        await session.refresh(row)

    assert to_fortuneo.transfer_pair_id is not None
    assert to_fortuneo.transfer_pair_id == arrival.transfer_pair_id
    assert to_tr.transfer_pair_id is None


@pytest.mark.asyncio
async def test_two_indistinguishable_legs_are_asked_about_rather_than_guessed(
    session: AsyncSession, test_user, ws
):
    """When nothing separates them, the answer is a question.

    This is the case the old code decided by row order, and the one the
    reporter asked us to leave alone: *"if the code has no way to tell
    the two debits apart, it is left unpaired for the user to resolve."*
    It is better than unpaired, because the queue says so.
    """
    source = await _account(session, test_user.id, ws.id, "Source")
    target = await _account(session, test_user.id, ws.id, "Target")

    first = await _txn(
        session, test_user.id, ws.id, source,
        amount="100.00", kind="debit", when=TODAY, description="VIREMENT 8832",
    )
    second = await _txn(
        session, test_user.id, ws.id, source,
        amount="100.00", kind="debit", when=TODAY, description="VIREMENT 8833",
    )
    await _txn(
        session, test_user.id, ws.id, target,
        amount="100.00", kind="credit", when=TODAY, description="RECU VIREMENT",
    )

    assert await detect_transfer_pairs(session, ws.id) == 0
    await session.commit()
    await session.refresh(first)
    await session.refresh(second)
    assert first.transfer_pair_id is None
    assert second.transfer_pair_id is None

    queue = await _pending(session, ws.id)
    assert len(queue) >= 1
    assert all(row.expectation_kind == "transaction" for row in queue)
    assert all(row.node == NODE for row in queue)


# ---------------------------------------------------------------------------
# #648: the reimbursement that looked like a transfer
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_card_leg_is_offered_rather_than_linked(
    session: AsyncSession, test_user, ws
):
    """A purchase and an unrelated refund of the same value are not a
    transfer, and linking them removed the purchase from the card's bill
    and the money from income at once, with nothing to review."""
    card = await _account(session, test_user.id, ws.id, "Card", kind="credit_card")
    checking = await _account(session, test_user.id, ws.id, "Checking")

    purchase = await _txn(
        session, test_user.id, ws.id, card,
        amount="374.66", kind="debit", when=TODAY, description="BAR DO ZE",
    )
    refund = await _txn(
        session, test_user.id, ws.id, checking,
        amount="374.66", kind="credit", when=TODAY + timedelta(days=1),
        description="PIX RECEBIDO",
    )

    assert await detect_transfer_pairs(session, ws.id) == 0
    await session.commit()
    await session.refresh(purchase)
    await session.refresh(refund)
    assert purchase.transfer_pair_id is None
    assert refund.transfer_pair_id is None

    queue = await _pending(session, ws.id)
    assert [row.strategy_id for row in queue] == ["card_leg_needs_confirming"]


# ---------------------------------------------------------------------------
# Turning it off, which was never possible before
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_workspace_can_switch_transfer_pairing_off_entirely(
    session: AsyncSession, test_user, ws
):
    """No rules, no pairing and no queue: a supported answer, not a
    workaround."""
    for strategy in reconciliation_policy.MATCH_TRANSFER["strategies"]:
        await rule_service.upsert_override(
            session, ws.id, test_user.id, NODE, strategy["id"], {"enabled": False}
        )
    await session.commit()

    source = await _account(session, test_user.id, ws.id, "Off A")
    target = await _account(session, test_user.id, ws.id, "Off B")
    debit = await _txn(
        session, test_user.id, ws.id, source,
        amount="50.00", kind="debit", when=TODAY,
    )
    await _txn(
        session, test_user.id, ws.id, target,
        amount="50.00", kind="credit", when=TODAY,
    )

    assert await detect_transfer_pairs(session, ws.id) == 0
    await session.commit()
    await session.refresh(debit)
    assert debit.transfer_pair_id is None
    assert await _pending(session, ws.id) == []


# ---------------------------------------------------------------------------
# The one guardrail
# ---------------------------------------------------------------------------
def test_an_approximate_rule_may_not_link_without_a_single_candidate():
    """The damage is silent: both rows leave income and expense, the
    totals move, and nothing says a guess was made."""
    with pytest.raises(rule_service.RuleError) as raised:
        rule_service.validate_config(
            {
                "outcome": "link",
                "when": {
                    "different_account": True,
                    "amount": {"match": "tolerance", "percent": "5"},
                },
            },
            whole=True,
        )
    assert raised.value.code == "unsafe_link"


def test_the_same_rule_is_allowed_once_it_insists_on_one_candidate():
    clean = rule_service.validate_config(
        {
            "outcome": "link",
            "when": {
                "different_account": True,
                "amount": {"match": "tolerance", "percent": "5"},
                "unique_candidate": True,
            },
        },
        whole=True,
    )
    assert clean["when"]["unique_candidate"] is True


# ---------------------------------------------------------------------------
# The page, for a workspace that has no modules at all
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_personal_workspace_sees_and_can_change_the_transfer_rules(
    client: AsyncClient, auth_headers
):
    """The reason the router stopped asking for a module. Transfer
    pairing runs for this workspace and always has, so hiding its rules
    hid an automation from the person whose data it edits."""
    listing = await client.get("/api/reconciliation/rules", headers=auth_headers)
    assert listing.status_code == 200, listing.text

    nodes = {group["node"]: group for group in listing.json()}
    assert NODE in nodes
    shipped = {rule["id"] for rule in nodes[NODE]["rules"]}
    assert "exact_amount_nearby" in shipped
    # The invoice set stays behind its module.
    assert reconciliation_policy.MATCH_INVOICE["node"] not in nodes

    resp = await client.patch(
        f"/api/reconciliation/rules/{NODE}/exact_amount_nearby",
        headers=auth_headers,
        json={"enabled": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_the_wider_window_rule_ships_visible_and_switched_off(
    client: AsyncClient, auth_headers
):
    """Somebody who moves money between countries turns it on knowing
    what they are buying; everybody else is not asked to pay for it."""
    listing = await client.get("/api/reconciliation/rules", headers=auth_headers)
    rules_by_id = {
        rule["id"]: rule
        for group in listing.json()
        if group["node"] == NODE
        for rule in group["rules"]
    }
    assert rules_by_id["close_amount_wider_window"]["enabled"] is False
    assert rules_by_id["close_amount_wider_window"]["outcome"] == "suggest"


@pytest.mark.asyncio
async def test_exporting_from_one_card_carries_only_that_card(
    client: AsyncClient, auth_headers
):
    """Each set is its own card with its own button.

    A button sitting under *Transfer rules* that quietly hands over the
    invoice rules as well is a button that lies, and the file is the
    thing people pass to each other.
    """
    whole = await client.get("/api/reconciliation/rules/export", headers=auth_headers)
    assert whole.status_code == 200, whole.text
    assert NODE in {n["node"] for n in whole.json()["nodes"]}

    scoped = await client.get(
        "/api/reconciliation/rules/export",
        headers=auth_headers,
        params={"node": NODE},
    )
    assert scoped.status_code == 200, scoped.text
    assert {n["node"] for n in scoped.json()["nodes"]} == {NODE}


@pytest.mark.asyncio
async def test_importing_on_one_card_cannot_rewrite_another_set(
    client: AsyncClient, auth_headers, session: AsyncSession, test_user
):
    """The scope is the card, not the file.

    Otherwise a file carrying every set, dropped on the transfers card,
    silently replaces rules the reader was not looking at.
    """
    file = (
        await client.get("/api/reconciliation/rules/export", headers=auth_headers)
    ).json()
    for node in file["nodes"]:
        for rule in node["rules"]:
            rule["enabled"] = False

    resp = await client.post(
        "/api/reconciliation/rules/import",
        headers=auth_headers,
        params={"node": NODE},
        json={"payload": file, "overwrite": True},
    )
    assert resp.status_code == 200, resp.text

    listing = (
        await client.get("/api/reconciliation/rules", headers=auth_headers)
    ).json()
    by_node = {group["node"]: group for group in listing}
    assert all(not rule["enabled"] for rule in by_node[NODE]["rules"])

    other = reconciliation_policy.MATCH_RECURRING["node"]
    if other in by_node:
        # Untouched: the file asked, the scope refused.
        assert any(rule["enabled"] for rule in by_node[other]["rules"])
