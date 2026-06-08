---
layout: post
title: "Flagship"
date: 2026-06-02
description: "Master Skywalker, there are too many of them! What are we going to do?"
tags: [cybersecurity, project]
---

Coming straight from my 17 year old hacking phase, something that interested me were EDRs (Endpoint Detection and Response Systems).

These pieces of software are deployed on host machines to provide runtime detection and response to cyberthreats.

While an incredibly complex software to program on one's own, I took on this task with some of my engineering / cybersec friends to see how far we could get in ~2 months.

Here's what came of it:

- **3 eBPF-based syscall monitoring** on host machines (open by John Tyler, connect by Mehar Klair, and execve by me)
- **a low latency gRPC pipeline** for sending telemetry from host machines to a detection server
- **and a detection server** that constructs process traces and uses vector embeddings to find semantically similar events to determine potentially anomalous behavior

Huge thanks to Kien Do, a very cool security researcher / engineer at TrendMicro/TrendAI for answering my many questions about how production grade EDRs work under the hood. This was by far my favorite side project EVER.

Will post more about some of the nitty gritty architectural decisions in the future.

Thanks for reading :)
