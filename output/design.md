# Design: Campus Customs Ops Desk

**One-line idea:** the dashboard is the shop's back-office desk at night. Paper tickets
hang on a spike, five agents sit at their stations on "the floor," a brass cash register
glows in the corner, and checks wait in a tray for a human signature. Every element
borrows from a real physical object in a small shop, so the person at the desk understands
it before they read a single label.

Stack: React + Vite + TypeScript in `frontend/`, no UI library, so every visual choice is
deliberate CSS. It talks to the FastAPI backend at `http://localhost:8000` (set by
`VITE_API_BASE`). The backend's CORS settings allow the Vite origin
`http://localhost:5173`.

---

## Layout: three zones, read left to right like the work itself

```
┌──────────── top bar: brand · SHOP DATE (desk.date_today) · gpt-6-luna · backend live · Reset desk ───────────┐
│ TICKET SPIKE │ BRIEF: selected ticket + "Send to the team →"                │ CASH DRAWER (register)        │
│  #101 paper  │ THE FLOOR: Boss on top, 4 specialists below, live wires      │  balance · meter · ledger     │
│  #102 paper  │ LIVE FEED  |  AFTER-ACTION SUMMARY (tabs)                     │ APPROVAL TRAY (checks)        │
│  #103 paper  │                                                               │  "Signing as ____"            │
└──────────────┴───────────────────────────────────────────────────────────────┴───────────────────────────────┘
```

- **Left: incoming work.** The three tickets are the inbox.
- **Center: the work happening.** One selected ticket, the agents working it, and the
  conversation.
- **Right: what needs *you*.** Money and approvals, the only things the human must act on.

This mirrors the flow of a ticket (arrives → team works it → human signs off), so your
eyes move in the same direction as the work. The rail and the right column are sticky,
so cash and approvals stay visible while you scroll the feed. Under 1280px the right
column drops below the center, and under 900px everything stacks.

---

## How each piece shows up

### Tickets: paper on a spike
- Each ticket is a cream **receipt** with a torn zig-zag bottom (CSS mask), a colored top
  edge by type (teal = customer order, blue = rent notice, pink = discount request), and a
  slight alternating tilt, as if each slip was pushed onto a spike by hand. A faint vertical
  line behind them is the spike.
- The requester's words are set in italic serif quotes, so the human voice of the
  request reads differently from system data. SKU, size, lease, and invoice links sit in
  small mono tags.
- The selected ticket straightens out, scales up slightly, and gets a gold outline.

### Resolved tickets: a rubber stamp
- When a run finishes, the ticket gets a red **RESOLVED** stamp that *thunks* down
  (scales from 2.2× to 1× with an overshoot) at an angle, with `mix-blend-mode: multiply`
  so it looks like ink on paper. The paper also dims to a used, filed-away tone.
- While a ticket is with the agents, a blue **WITH THE TEAM** stamp breathes (pulses
  opacity). **ESCALATED** is an amber stamp.
- The rail header keeps count: "2 open · 1 resolved."
- The brief header shows the same status as a pill, and the run button turns into
  "Resolved ✓" (with the hint "Reset the desk to run it again") so a finished ticket can't
  accidentally be re-run.

### The floor: five agents, five stations
- The **Boss** sits top-center on a wider card; the four specialists sit in a row below.
  Behind them is a faint dotted **mesh connecting every agent to every other agent**. It
  is a visual of the "full connectivity" design, so you can see the team *could* talk
  to anyone.
- When an agent delegates, that edge lights up in **the delegator's color** and its
  dashes **flow** toward the receiver while the run is live (an animated SVG
  `stroke-dashoffset`). Specialist-to-specialist handoffs arc beneath the row, so they
  read differently from Boss orders.
- Each station shows a **status pill** (Not called / Working / Done / Error), a **speech
  bubble** with what the agent is saying or doing right now ("Checking check stock,
  list vendors…", "Asked accounting: queue invoice 501…", or its final summary), the last
  MCP tools it used as chips, and how many briefs it received.
- **Working** agents lift, glow in their color, and get a pulsing ring around their
  avatar plus typing dots. **Not called** agents stay slightly faded. That's deliberate:
  the plan said not every specialist should work every ticket, and the floor makes that
  visible at a glance.

### How agents read differently: each one has a voice on paper
Every agent has a color, an icon, *and* a paper texture for its words, in both the
station bubble and the live feed:

| Agent | Color / icon | "Voice" styling | Why |
|---|---|---|---|
| Boss | gold · crown | serif **memo** with a gold rule | Decisions read like a manager's memo |
| Inventory | teal · box | mono font on a **stock-slip** with ruled lines | Feels like a warehouse count sheet |
| Accounting | green · ledger | **ledger paper** with green rules and tabular numbers | Numbers line up like a ledger |
| Facilities | blue · building | **blueprint grid** background | The person who owns the space |
| Customer Service | pink · chat bubble | rounded **chat bubble** shape | Speaks to customers, so it looks like a message |

So you can tell who is talking from the shape and texture of the words even without
reading the name.

### Live feed: the conversation, threaded
- The live feed is a vertical thread: each agent line has a colored left rule and an
  avatar, and is **indented by delegation depth** (Boss at 0, a specialist the Boss
  briefed at 1, a specialist *they* briefed at 2), so the chain of command is visible.
- **Handoffs** are dashed cards ("Boss → Accounting") with the full brief text, so you
  can read exactly what was asked.
- **Guardrail moments** show inline in italics, e.g. "signature corrected to
  facilities" when the MCP layer re-stamps an agent's identity, so safety is visible,
  not hidden.
- Run markers open and close the thread with the real cost: "18 model calls · 30 tool
  calls · 50,736 tokens."

### After-action summary: what each agent did
- When a run finishes, the center switches to the summary tab automatically. It
  contains:
  - **"The Boss's call"** card with a stamp (RESOLVED / ESCALATED), the decision in bold
    serif, the plain-language summary, and a yellow **"Waiting on you"** box listing the
    exact approvals needed.
  - **One report card per specialist**, with their summary, the actions they took, and the
    tools they used. Specialists who weren't called get a dashed, faded card that says
    "Not called on this ticket."
  - **Drafts on the board**, shown as lined letter paper with "Draft #3 · by facilities ·
    not sent." Drafts *look* unsent, which reinforces the rule that nothing goes out.

### Cash: a cash register that rolls down
- The balance is a **green-phosphor register display** (glowing mono digits on black
  behind a brass bezel, with faint scanlines). It reads `checking` from `cash_accounts`
  via `GET /api/cash`.
- When a payment is approved, the digits **roll down** to the new balance (eased
  animation), and a red **"−$840.00"** drops out of the display and fades.
- Under it, a **meter** shows the balance as a green bar with the *pending* amount as an
  amber hazard-striped segment, so you can see how much of the cash is already spoken for.
  Three stat tiles show pending, free after pending (turns red if negative), and paid out.
- A **ledger** lists every paid item with the payee, the kind, and "signed Kelly Yang."
- Footnote: "Cash only goes out in this shop. No revenue is modeled."

### Approvals: sign the check
- Pending payment requests appear as **bank checks** on green security paper: "Pay to
  the order of Bulldog Print Co," the amount in a box, **the amount written out in words**
  ("Eight hundred forty and 00/100 dollars"), a memo line with the agent's reason, and
  "Prepared by accounting."
- You type your name once in **"Signing as"** (saved in your browser). It appears in
  handwriting-style italic on each check's signature line, and **Approve & pay** stays
  disabled until there's a signature. That makes the human-approval rule something you
  *feel*: the agents prepared it, you sign it.
- A check tied to the selected ticket gets a gold outline. If a check is bigger than the
  balance, it warns "The register will refuse it." If the backend refuses (not enough cash,
  vendor still blocked), the reason appears in a red toast.
- Reject opens an inline reason field. No money moves.

### Small touches that make it pleasant
- The **shop date** in the header is `desk.date_today` ("Monday, August 31, 2026"), not
  the real date, so you're always in the shop's time.
- A **gpt-6-luna** chip and a "backend live" dot sit in the top bar. If the backend is
  down, a banner tells you the exact command to start it.
- **Toasts** in plain English: "Ticket #101 is on the Boss's desk." · "Paid $840.00 to
  Bulldog Print Co. Checking is now $2,560.00." · "Payment refused: Not enough cash…"
- **Reset desk** asks for confirmation in a modal that says what happens (tickets reopen,
  payments cleared, audit trail kept).
- Night-shift palette: deep navy desk, warm cream paper, gold accents. It's calm enough
  to sit at for a long time, with color reserved for meaning (agent identity, money,
  status).
- The type pairs a classic serif (Iowan Old Style / Palatino) for human-facing words
  with a clean sans for UI and mono for data, tools, and money.

---

## Why these choices
1. **Physical metaphors lower the learning curve.** Everyone knows what a stamped
   receipt, a signed check, and a cash register mean, so the status of every ticket and
   every dollar is obvious at a glance.
2. **The human's job is separated from the agents' job.** The right column holds only
   the things that need a person (money and approvals), and the signature line makes
   approval a deliberate act, not a stray click.
3. **You can watch, not just read.** The floor turns an abstract multi-agent run into
   people at desks handing notes to each other, which is easier to follow and more fun
   than a log.
4. **Efficiency is visible.** Faded "Not called" stations and cards make it obvious when
   the Boss used only the specialists a ticket needed. That's exactly what the plan in
   `desk_tickets.html` predicted, so plan vs. actual is easy to compare.
5. **Safety is visible.** Unsent-letter drafts, refused-payment toasts, and guardrail
   lines in the feed show the rules working instead of asking you to trust them.
