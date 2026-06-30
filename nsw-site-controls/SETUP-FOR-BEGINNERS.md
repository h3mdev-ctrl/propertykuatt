# NSW Site Controls — set it up from scratch (total beginner guide)

Hi! This guide gets you a little tool that, when you give it a NSW property
(a lot number, an address, or a map pin), tells you the planning rules for that
exact site — what zone it's in, the floor-space ratio, the maximum building
height, the minimum lot size, heritage flags, and the City of Ryde setback /
parking / landscaping rules — so you can design to the site.

**You do NOT need to know anything about computers.** The trick: you install one
thing (an AI assistant called *Claude Code*), and then you let *it* do all the
fiddly setup by copy-pasting the instructions below. Claude can run the commands
for you, fix errors, and explain anything.

The code lives here:
👉 **https://github.com/h3mdev-ctrl/propertykuatt** (in the `nsw-site-controls` folder)

---

## The big idea (read this first, it's 20 seconds)

Think of **Claude Code** as a very capable assistant sitting at your computer.
You talk to it in plain English ("install Python", "set up this tool", "run it
for 59 Falconer St"), and it does the typing for you. So most of this guide is
really just *things to say to Claude*. When in doubt, paste the error you see
back to Claude and say "fix this".

---

## Step 1 — Install Claude Code (your AI helper)

This is the only thing you install by hand.

1. Go to **https://claude.ai/code** and download the **Claude Code desktop app**
   for your computer (there's a Mac version and a Windows version).
2. Install it like any normal app (double-click the downloaded file, follow the
   prompts).
3. Open it and sign in with a Claude account. (You'll need a paid Claude plan —
   the "Pro" or higher subscription — for it to actually do work. A free account
   won't be enough.)

You now have your assistant. Everything below, you can paste to it.

> **Tell Claude which computer you have.** The very first thing to say:
> *"I'm on a Mac"* or *"I'm on Windows 11"*. It changes a few commands and Claude
> will pick the right ones automatically.

---

## Step 2 — Let Claude install the plumbing

The tool is written in a language called **Python**, and the code is fetched
with a tool called **git**. You don't need to understand either — just ask Claude
to install them. Paste this:

> **"Please check whether Python (version 3.10 or newer) and git are installed
> on my computer. If either is missing, install it for me and tell me what you're
> doing in plain English. I'm on [Mac / Windows — pick one]."**

Claude will run a couple of checks and, if needed, install them. If it asks for
your permission to run a command, say yes. If anything errors, paste the error
back and say *"fix this"*.

---

## Step 3 — Get the tool's code from GitHub

GitHub is just a website where code is stored. We want to copy ("clone") it onto
your computer. Paste this to Claude:

> **"Clone the GitHub repository https://github.com/h3mdev-ctrl/propertykuatt
> into my Documents folder, then go into the `nsw-site-controls` folder inside it.
> That folder is the tool I want to set up."**

(If GitHub asks Claude to log in, Claude will walk you through a one-time sign-in
called `gh auth login` — just follow its prompts. The repo is public, so usually
no login is needed to read it.)

---

## Step 4 — Turn it on (install + first run)

Now we install the tool's bits and check it works. Paste this:

> **"Inside the `nsw-site-controls` folder, set the tool up by running
> `pip install -e ".[dev]"`, then run its test suite with `pytest` to confirm
> everything works. Show me the result."**

You should see something like **"49 passed"**. That means it's healthy. (Two
tests may say "skipped" — that's normal; those only run when you specifically
ask for live internet checks.)

---

## Step 5 — Use it 🎉

Now the fun part. You can ask Claude to run it on any NSW site. Examples to paste:

> **"Run the controls tool for the address: 59 Falconer St, West Ryde NSW,
> assuming a dwelling house."**

> **"Run the controls tool for lot 3 / DP24994 as a dual occupancy."**

> **"Run it for these map coordinates: longitude 151.0931, latitude -33.8076."**

Claude will print a **Site Control Sheet** — zone, floor-space ratio, maximum
height, minimum lot size, the estimated maximum floor area you can build, and
(for Ryde) the setback / deep-soil / parking rules with the exact council clause
numbers.

**Three things to know about the answers:**
1. The most reliable way to identify a site is its **lot/DP number** (you can
   read it off the free NSW map at **maps.six.nsw.gov.au**). Addresses get
   "geocoded" approximately, so always sanity-check the lot it found.
2. The detailed setback/parking rules are currently only for the **City of Ryde**.
   Zoning, FSR, height and lot size work **anywhere in NSW**.
3. It's a **planning helper, not legal advice**. Always confirm with a planner
   or a council certificate before you design for real. It even warns you when a
   site might be affected by the newer NSW "Low and Mid-Rise Housing" rules,
   which can allow more than the base zoning shows.

---

## Step 6 (optional, recommended) — Install gstack, Garry Tan's "AI engineering team"

This part isn't required to use the tool — but if your friend (you!) wants Claude
Code to be dramatically better at building and fixing software in general, install
**gstack**. It's a free, open-source pack of "skills" made by Garry Tan (the
president of Y Combinator) that turns Claude Code into a whole virtual team — a
planner, a designer, a code reviewer, a tester, a "ship it" release manager, and
more — all triggered with simple `/commands`.

GitHub: **https://github.com/garrytan/gstack**

Easiest way: paste this to Claude:

> **"Install Garry Tan's gstack by running:
> `git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack && cd ~/.claude/skills/gstack && ./setup`
> Then tell me what new `/` commands I can use."**

After it's in, you'll have commands like `/office-hours` (sanity-check an idea),
`/plan-eng-review` (lock a plan before building), `/review` (find bugs), `/qa`
(test a website in a real browser), and `/ship` (package and publish changes).
You just type the slash command and Claude does the rest.

---

## The one-shot version (paste this whole block to a fresh Claude)

If you'd rather not go step by step, open Claude Code and paste this single
message — it does Steps 2–5 in one go:

> *"I'm a complete beginner on [Mac / Windows]. Please set up a tool for me,
> explaining each step in plain English and handling any errors yourself:*
> *1. Make sure Python 3.10+ and git are installed; install them if missing.*
> *2. Clone https://github.com/h3mdev-ctrl/propertykuatt into my Documents folder.*
> *3. Go into its `nsw-site-controls` subfolder and run `pip install -e ".[dev]"`.*
> *4. Run `pytest` and confirm the tests pass.*
> *5. Then run the tool for the address '59 Falconer St, West Ryde NSW' as a
> dwelling house and show me the result.*
> *Read the `README.md` in that folder first so you know how it works."*

---

## If something breaks

- **Copy the red error text, paste it to Claude, and say "fix this."** This works
  for ~95% of problems. Claude wrote/knows this tool and can self-correct.
- "Command not found: python" / "pip" → ask Claude to install Python and try again.
- "Permission denied" on a command → say yes when Claude asks to approve it.
- The tool says a site has "no data" or a service "timed out" → the NSW government
  map servers are occasionally slow; ask Claude to "try again", it retries
  automatically.

---

## Cost & privacy, briefly

- The **tool itself is free** and reads only **public** NSW government planning
  data. It doesn't need any paid key or account.
- The thing you pay for is the **Claude subscription** that powers your assistant.
- Nothing about your sites is sent anywhere except the public NSW map services
  the tool queries.

That's it — enjoy. When in doubt, just ask Claude. 🏡
