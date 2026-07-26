---
title: "Copy Fail Fails on Android, why?"
date: 2026-07-17
description: "a little pondering"
tags: [writeup, android, linux]
---

![copy-fail](/img/copy-fail.png){ width="500" }

Something that got me kinda worried was that vulnerabilities like the infamous "Copy Fail" of 2026, an LPE (Local Privilege Escalation) bug in the Linux may be exploitable in Android, given that they come from similar roots with Android being based off of the Linux kernel.

Turns out that we don't have to worry about this! Here's why:

The specific kind of LPE bug that Copy Fail exploited was the user controlled 4-byte write to in-memory page caches of files due to a bug in the crypto subsystem.

This could be used to overwrite binaries like `su` in RAM to gain root access to a system.

Android, however, uses strict SELinux policies (using things like Mandatory Access Control) that significantly reduce the attack surface. This prevents things like the ~732 byte python script POC that work on staple Linux distros (Ubuntu, RHEL, Debian) from working on Android.

Specifically, the following are restricted:

\- AF_ALG socket access (the kernel interface which allows unprivileged user-space programs access to the kernel's cryptographic API). Most apps and system components are blocked by default.

\- No setuid/setgid binaries, think `su` which allow easy privilege escalation, are event present in Android, so it would be significantly harder to find a viable candidate for the arbitrary page cache write.

\- Additional hardening via sandboxing, app isolation, verified boot, and other Android specific mitigations further limit what untrusted code can do.


TLDR, no need to panic about this vuln from an Android perspective :)
