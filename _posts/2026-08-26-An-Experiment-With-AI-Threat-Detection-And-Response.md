---
title: "Kernel Harbor -- An EDR with LLM analysis of kernel events"
date: 2026-08-26
description: ""
tags: [writeup, Go, C, low-level, cybersecurity]
---

Something I'd been toying around with recently is the idea of AI threat detection and response, so I decided to build my own Endpoint Detection and Response system using kernel level event monitoring from my favorite vendors (Falco / Cilium) and implemented a RAG based analysis of the telemetry that comes in.

## Rounding up the Avengers lol

This project was inspired by my security work at IBM where I'd been working on anti-abuse systems for Kubernetes, particularly the use of eBPF.

I posted about my idea of starting a project using that technology on LinkedIn, and to my surprise a bunch of people wanted to join in on the fun!

Unfortunately I wasn't able to let absolutely everyone who wanted to participate as a big BIG team would be too unwieldy, so this was the team I ended up forming:

- AI Security Software Engineer @ Trend AI -- Kien Do
- GPU Programmer Intern @ AMD -- John Tyler
- Incident Response Intern @ KPMG -- Mehar Klair
- Infra/Security Software Engineer Intern @ IBM -- Yours Truly

Couldn't have asked for a better team :)

## There are layers to this

One thing I didn't want to do though is attach an LLM directly to every single event that comes in. That would be a logistical nightmare costing a zillion dollars in inference costs.

There are moments to use AI and moments when not to.

Sort of like how there's a fast and slow path when reacting to something. If it looks like a duck, quacks like a duck, then it's probably a duck and we can choose the fast path. But if it only quacks like a duck, well now we're not sure and go with a slow path.

I'll let you fill in the blanks as to what the path means for the duck. Depends if you're hungry or not.

But anyways, there are a couple ways we can do a layered approach.

Initially I was thinking of two layers.

- One for heuristic rules that trigger responses immediately for things like Regex-based patterns for obviously malicious commands
- And another for LLM analysis for when we want to search our database via RAG for semantically similar past events (and check if it matches as malicious)

But there was one flaw with this approach.

It doesn't maintain temporal context.

We wouldn't be able to understand a multi-step attack chain occurring within a 30-second window for example if we don't keep track of chained events.

That said, I modified the plan to have a 3-layer approach with:

- Heuristic Rules (Immediate)
- Correlation Engine (Immediate)
- AI/LLM Analysis (Delayed)

## So is it a duck?

Now onto the LLM analysis. This was the last layer and by far the slowest one. And no, it wasn't a per-event thing -- that would've cost a zillion dollars and probably melted my terrible laptop. 

My model of choice, was qwen2.5:1.5b (text generation) with nomic-embed-text (for embeddings). I mainly chose the model because I had a terrible laptop when I started this project LOL. It's likely undersized, but it worked for my initial testing. As for the embeddings, it was fine to use nomic-embed-text over nomic-embed-code since it wasn't really source code, and more of human readable strings that were being fed to it.

The data I wanted this model to do was mainly create behavior summaries based on the events that come in.

## One batch two batch penny and dime

The trick to lower latency and increase throughput was batching. Instead of hitting the LLM with every single event, events pile up and get sent to the model in groups. On the analysis side, a batch processor accumulates events per host and fires when it hits either 100 events or a 30-second window, whichever comes first. Then a few worker goroutines chew through the batches.

ne inference per batch, and every event still ends up in front of the model eventually.

## Slow down, even for a second

Here's what happens to a batch once it gets picked up.

First, every event gets turned into that behavior summary I talked about, short tags describing what the event *means*, not just what it was:

```
event_type:execve reverse_shell image:bash
event_type:connect remote_code_execution image:curl
```

Then I embed each summary and search Elasticsearch for the five most semantically similar past events from the same host. This lets the model go like "hey, this looks an awful lot like that thing last week that was definitely bad."

I also pull in process ancestry, parents and their children, so it can spot weird spawning patterns like a server dropping into a shell. The correlation engine's chain detections get fed in too, so the model knows when events are part of a coordinated multi-step attack instead of random noise.

All of that gets assembled into one big prompt: the batch, similar events, process trees, and correlation chains as tables, plus guidelines and a strict JSON output format. 

The model then answers with a verdict (`benign` / `suspicious` / `malicious`), a confidence score, evidence, and, the important part, the exact event IDs it thinks are compromised.

## Pull the trigger

When the model says `malicious` with confidence 0.7 or higher, we act.

The agent polls the analysis server for actions every five seconds. Kills come with a PID *and* process start time, so the agent double-checks against `/proc` before sending SIGKILL, i.e. no killing some innocent process because Linux recycled its PID.

Malicious connections get their IP blocked in two ways:
- iptable rules
- feeding the address into an XDP eBPF map so packets discarded in the kernel before they even reach user space.

## Anddd what did we learn?

A combination of both deterministic and AI assisted detections is necessary in today's day and age. Attackers use agents to perform recon and try exploitation paths in minutes, so detection to response speed is critical.

Model size matters, but context matters more. A 1.5b model is small and it showed structured JSON reasoning was the weak spot. But RAG context plus a strict prompt got it most of the way there. I'd reach for something bigger if I were to do it again. Cut me some slack though, I did say I had a terrible laptop xd.

Wanna see the code? [KernelHarbor](https://github.com/fr4nsyz/KernelHarbor)
