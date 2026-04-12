"""Outlook category buckets for Logistics/Trucking after-hours shared mailbox classification."""

from __future__ import annotations

from .models import CategoryDefinition

# Order matters: first entry is the Gemini/parse fallback (see gemini_category_batch.py).
DEFAULT_CATEGORIES: list[CategoryDefinition] = [
    CategoryDefinition(
        name="General",
        description=(
            "Catch-all when no specialized bucket clearly fits: vague subjects, mixed threads, "
            "or low-signal content. Prefer a specific category when the primary intent is obvious. "
            "Use when a multi-row tracker has no dominant problem in the latest reply and "
            "**BulkStatusDigest** does not fit."
        ),
    ),
    CategoryDefinition(
        name="Critical",
        description=(
            "Safety and major incidents: accidents, injuries, fatalities, hazmat releases, "
            "law enforcement, imminent life-safety risk, or severe liability exposure requiring "
            "immediate escalation—not routine delays or equipment inconvenience. May apply when "
            "the driver cannot safely remain in the cab due to fumes, chemical smell, or similar "
            "acute health risk if escalation is warranted."
        ),
    ),
    CategoryDefinition(
        name="EquipmentBreakdownRoadside",
        description=(
            "Truck/trailer down, mechanical failure, reefer/temperature unit failure, tow, "
            "or roadside vendor—equipment not rolling. Do **not** use for an entire multi-row "
            "tracker only because one line says breakdown or recovery—prefer **BulkStatusDigest**, "
            "**PickupDeliveryExecution**, or **General** unless the **latest top-level reply** is "
            "clearly about equipment down or recovery (not just pasted table text)."
        ),
    ),
    CategoryDefinition(
        name="ETAOrTracking",
        description=(
            "Requests or updates about driver location, miles to stop, ETA to pickup/delivery, "
            "check-call style status, or 'where is the load/truck'—including customer/broker "
            "tracking follow-ups. Prefer **Driver** when the latest message is only internal staff "
            "relaying the driver’s location, miles out, or ETA."
        ),
    ),
    CategoryDefinition(
        name="AppointmentScheduling",
        description=(
            "Scheduling or changing pickup/delivery appointments, work-ins, shipper/receiver "
            "windows, or confirming slot times—not a simple ETA ping on an existing appointment."
        ),
    ),
    CategoryDefinition(
        name="PickupDeliveryExecution",
        description=(
            "Active load execution: dispatch, driver assignment, pickup/delivery progress, "
            "delay at shipper/receiver, load ready notifications, seal/OS&D execution—when "
            "the focus is moving the shipment, not only an ETA or tracking question."
        ),
    ),
    CategoryDefinition(
        name="TrailerEmptyYard",
        description=(
            "Empty trailer requests, trailer pools, OOS or dropped trailer removal, yard/drop-lot "
            "inventory positioning, or 'where can we get an empty'—including broker or partner "
            "asks when the main ask is equipment positioning, not a service escalation."
        ),
    ),
    CategoryDefinition(
        name="DocumentationPaperwork",
        description=(
            "Non-customs paperwork: BOL corrections, POD requests, load numbers, seal issues, "
            "tender/SCAC or IT/system identifiers needed for movement—when not primarily "
            "a border/customs hold. Prefer **CustomsBorder** when the blocker is clearance or "
            "international documentation."
        ),
    ),
    CategoryDefinition(
        name="CustomsBorder",
        description=(
            "Cross-border execution blocked on customs, border clearance, broker packets, duties, "
            "or international paperwork before or during crossing. Apply only when the **latest** "
            "substantive content is primarily about that—not when the newest reply is only internal "
            "triage on a thread that quoted customs earlier. Prefer **InternalHandoffRouting** or "
            "**General** for short internal routing replies."
        ),
    ),
    CategoryDefinition(
        name="RateQuoteTender",
        description=(
            "Spot quotes, RFQs, lane bids, tender announcements, or pricing discussions—not "
            "execution of an already-booked load."
        ),
    ),
    CategoryDefinition(
        name="CancellationRecovery",
        description=(
            "Load cancellation, need to recover/repower, or explicit 'should we recover' / "
            "coverage crisis on an existing commitment."
        ),
    ),
    CategoryDefinition(
        name="BulkStatusDigest",
        description=(
            "Multi-row tracker emails, store/PRO tables, or bulk status grids where many loads "
            "or stops appear in one message and no single operational fix dominates the latest "
            "reply."
        ),
    ),
    CategoryDefinition(
        name="AccessorialApproval",
        description=(
            "TONU, detention, lumper, or other accessorial/charge approvals or disputes "
            "requiring customer or facility confirmation."
        ),
    ),
    CategoryDefinition(
        name="Driver",
        description=(
            "Driver communications: check-calls, routing or directions, check-in at shipper/"
            "receiver, general field questions—when the thread is about routine operational status "
            "rather than welfare/safety. **Prefer this over ETAOrTracking** when the latest "
            "message is only Logistics/Trucking or Swift Transportation staff relaying the driver’s "
            "location, miles to destination, or ETA, even on customer-facing threads."
        ),
    ),
    CategoryDefinition(
        name="DriverWelfareSafety",
        description=(
            "Driver illness, unsafe cab (fumes), hotel/rest, or welfare focus—not routine ETA "
            "updates. Prefer **Critical** when life-safety or medical urgency is plausible."
        ),
    ),
    CategoryDefinition(
        name="CustomerBroker",
        description=(
            "External party pressure or service recovery: shipper, receiver, or broker "
            "escalations, temperature or claim disputes, service failures demanding "
            "coordinated response—not internal HR/payroll. For empty trailer or yard positioning "
            "asks without escalation tone, prefer **TrailerEmptyYard**."
        ),
    ),
    CategoryDefinition(
        name="Internal",
        description=(
            "Company-internal coordination: payroll/HR/deductions, IT/password resets, "
            "training, policy questions, or handoffs for the day shift—not short routing or "
            "delegation on active operational threads (see **InternalHandoffRouting**)."
        ),
    ),
    CategoryDefinition(
        name="InternalHandoffRouting",
        description=(
            "Internal-only routing: add for visibility, delegate to day team or another queue, "
            "wrong-desk redirects, asking for a load/BOL to direct mail, or after-hours policy "
            "limits ('we cannot assist with…') when the latest message does not state a new "
            "external escalation or a customs/border problem."
        ),
    ),
    CategoryDefinition(
        name="AutomatedReportOrAlert",
        description=(
            "Message is primarily a system-generated report, digest, TMS/ELD/EDI alert, or "
            "no-reply notification—including forwards (FW:) where the body is still the original "
            "system report—unless a human clearly adds a new urgent question or task."
        ),
    ),
]
