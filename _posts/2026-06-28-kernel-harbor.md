---
title: Building my own EDR
date: 2026-06-28
description: A crazy + fun journey
tags: [project, team, EDR, Threat Detection, TrendAI (TrendMicro), AMD]
---

## Why bother?

I think one of the best ways to learn a new technology is to build it (or a subsection of it) yourself.

Reading a bit on how Endpoint Detection and Response systems work, I noticed a lot of them will have some sort of monitoring set up for the syscalls on their endpoints, a popular method being via eBPF.

So I embarked on this perilous journey of reading restricted C code that allows user space programs to access real-time data from kernel events (it wasn't *very* perilous, their documentation was actually pretty nice hehe).

## Everything's awesome, everything's cool when you're part of a team

Later in the week, I decided to post a bit about the new rabbit hole I was going to go down over the weekend, and that's when Kien Do, a security engineer from TrendAI (formerly Trend Micro), reached out to ask me if I'd like any help with the project.

At this point I was kiiiinda freaking out because it's not every day that someone from one of the coolest cybersecurity companies in the world DMs you about your project, oh my GODDDD-

But anyways we talked a bit about how production-grade EDRs work in practice, and that gave me a bunch of ideas as to how to design the system.

I also dragged a couple of my friends from the University of Alberta who might be interested in contributing to this project, one working cybersecurity incident response and the other working as a GPU programmer!

## Why does it feel like, somebody's watching meee

After our chats, I found that there's a couple categories of syscalls we would want to monitor.

- Process Executions (what I worked on)
- File Opens (John Tyler -- AMD dude)
- Network Connections (Mehar Klair -- Incident Response dude)

These three types of events should cover a pretty good portion of what goes on in a system. It's not FULLY comprehensive, but it's good enough for a subsection of an EDR.

```
eBPF breakdown:

A bit on how eBPF works...

eBPF (Extended Berkeley Packet Filter) was introduced to make the Linux kernel dynamically programmable without changing its source code or crashing the system.

Developers who wanted to introduce new capabilities in to the kernel for networking, security, and observability faced two very unappetizing choices:

1. modify the kernel source code - would require code changes to upstream Linux community which could take forever to actually get accepted
2. load a kernel module - write extra software to extend functionality at runtime at the cost of a potential bug or memory error resulting in a crashed system.

The solution, was eBPF, or as some say "JavaScript for the Kernel". To create a sort of balance between the two approaches, eBPF adopted a model similar to how JavaScript runs in a web browser. It introduced the Kernel Verifier to prevent things like memory errors, guaranteeing it won't crash the system, and a Just-In-Time (JIT) Compiler to maintain native speed.

With these, client programmers could write code in user space AND load it into the kernel.
```

## You shall not PASS

Alright, now what do we do with all this telemetry? How do we figure out if an executable is malicious?

There are two paths I wanted to try out.

1. Heuristic (inline) methods (regex patterns) for instantaneous detection and response of simpler data. I could rant about how annoying regex is to work with haha
2. RAG + LLM (with async batching) to generate behavior summaries, embed them with Ollama via nomic-embed-text, vector search for similar past events in our database (I chose to use Elasticsearch), and walk the process ancestry tree (aka the process' parent, grandparent, and great grandparent) looking for figuring out how a process came to exist.

e.g. bash (process) -> nc (parent) -> curl (grandparent) indicates a possible LOLBin chain.

It may not happen exactly linearly like this, it could be that a sibling of one parent is part of the chain as well. This is why I chose to do a breadth scan as well based off of a GUID I created which looks like `{hostname}-{pid}-{start_time_ns}`

But yea, if say another sort of chain happens, maybe:

e.g. sh (process) -> nc (parent) -> curl (grandparent)

We would be able to catch it based off of it being a similar event.

## Ban him ban him ban him ban him!!

Finally, response comes in two actions depending on how it was triggered.

| Trigger | Latency | Action Examples |
|---------|---------|----------------|
| Regex heuristic match | Same RPC response | `KILL_PID` |
| AI "malicious" verdict | ~5-8s (batch + poll) | `KILL_PID`, `BLOCK_IP` |

Also just a thing to add, the killing happens along the attack chain I talked about above, so every process that was involved in this malicious trigger gets handled.

## Retrospective

I'm pretty happy with this project. While it isn't by any means on the scale of Falcon by Crowdstrike, I'm happy with the progress we made on this project given we were a team of 4 and spent only 2 months on it.

Looking back though on the detection engine, I realized there's another embedding model I could have used called nomic-embed-code which might have better results. Will look into this in the future.

Overall, eBPF was super fun to learn about, had a lot of fun learning about production-grade EDRs from Kien Do, and loved the paired programming sessions with the team :)

Stay tuned for more blogs like this! They won't exactly have a schedule given project ideas just come into my head at random intervals, but they will come eventually xd

-- A Void Pointer
