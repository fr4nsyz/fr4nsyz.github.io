---
title: "When Miliseconds Matter"
date: 2026-07-18
description: "man i don't have enough context switches to spare"
tags: [writeup, linux, eBPF, observability]
---

![falco-logs](/img/falco-logs.png){ width="500" }

Every millisecond counts in the world of cybersecurity.

Your device could load a binary in ~1 ms, allocate memory and spawn threads in ~10-50 ms, compute the first hash of a challenge in ~100-200 ms, and connect to a mining pool in ~500-1500 ms.

It only takes ~2 seconds to start mining at full rate.

Can your system catch this before it happens?

I wanted to research more into this interesting topic of kernel level observability in the world of cybersecurity, so I decided to take a look inside one of the leading tools in this space, Falco.

If you aren't familiar with Falco, here's a short intro.

Falco is a kernel level event monitoring framework that allows you to monitor and detect exploits happening on your containers at the syscall level.

It does this by using a relatively new technology introduced to the Linux kernel called eBPF (extended berkeley packet filters). I would explain the name, but it really doesn't tell much about how it works, so I'll go right into explaining previous approaches to kernel observability and what eBPF provides.

You may have used programs such as strace which allow you to observe syscalls as they occur on your system, but did you know that this program can easily become backlogged?

On a system with a high volume of syscalls happening at a given time interval, strace has to context switch multiple times per syscall due to the way it works.

![strace-flow](/img/strace-flow.png){ width="500" }

4 context switches were required just for this ONE syscall.

You can imagine how much latency this can incur on a high traffic system such as a web server.

Alternatively, eBPF gives you the same observability capabilities without all the context switches.

eBPF programs run inside the kernel, in the same context as the syscall being monitored. This means there is no need to switch because everything is essentially in the same place.

![ebpf-flow](/img/ebpf-flow.png){ width="500" }

The eBPF program isn't a separate process. It's compiled bytecode that the kernel inserts into the syscall path itself. It runs on the same CPU, same kernel thread, as the syscall handler.

Now you might be wondering now, how does the kernel communicate it's findings to the user-space program that we were monitoring from?

Well the kernel actually stores all of this in memory which we as the user program can read!!

That's where `mmap` comes in.

`mmap` is a syscall which maps files or devices directly into a process's virtual memory space.

By reading from this mapped memory into the ring buffer (the data structure of choice for the kernel writes), we are able to receive our MULTIPLE syscalls with just 1 context switch. ISN'T THAT AWESOME???


Anyways, that's all I've got for y'all today. eBPF is such a cool technology :)
