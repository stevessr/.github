#!/usr/bin/env python3
"""
Assemble ARM64 hover-to-focus v4 code caves at exact libxrshell.so vaddr 0x387c40
and generate hover_caves.h for xrshell_dist_patch.c.

Features:
  - Full hitInfo check: hitPanel (+88), hitCaptionBarPanel (+104),
    hitResizeBarPanel (+112), and isHit bit 0 (+120 & 1).
  - Trigger (+2948) AND Inner Grip (+2908 > 0.35f) bidirectional focus lock
    with 14-frame (~155ms) release debounce (prevents inner-grip/trigger bounce
    and prevents stealing focus while gripping/triggering in VR or 2D).
  - Bidirectional entry/exit debounce (10 frames enter ~110ms, 14 frames exit ~155ms)
    + 20-frame (~220ms) post-switch cooldown to completely eliminate rapid ping-pong
    oscillation when VR apps (e.g. YouTube VR) have different ray/focus mapping.
  - Per-controller (0x02 Left / 0x04 Right) motion EMA + gMainInputSource tracking.
  - Hand tracking (0x10 / 0x20) & HMD (0x08) are excluded from hover preemption.
"""
import subprocess, tempfile, os, struct

ASM = r"""
.text
.align 2

/*
 * HoverState layout @ 0x433f00 (144 bytes):
 *   +0x00: uint32_t hover_focus
 *   +0x04: uint32_t last_active   (0=ctrl0, 1=ctrl1)
 *   +0x08: uint32_t valid[2]
 *   +0x10: uint32_t hit[2]
 *   +0x18: uint32_t mouse_hit
 *   +0x1C: uint32_t stable_cnt    (consecutive frames raw_focus != hover_focus)
 *   +0x20: uint64_t prev_main_src
 *   +0x28: float    ema[2]
 *   +0x30: uint32_t has_prev[2]
 *   +0x38: uint32_t btn_active[2] (trigger click OR inner grip > 0.35f)
 *   +0x40: float    prev_pose[2][8]  (slot 0: +0x40, slot 1: +0x60)
 *   +0x80: uint32_t cooldown      (post-switch anti-ping-pong lock frames)
 *   +0x84: uint32_t btn_hold      (trigger/inner-grip release debounce frames)
 *   +0x88: uint32_t cfg_enter     (frames to switch 0->1, live-configurable)
 *   +0x8C: uint32_t cfg_exit      (frames to switch 1->0, live-configurable)
 *   +0x90: uint32_t cfg_cool      (post-switch cooldown frames, live-configurable)
 */

.global cave1_sync_head
cave1_sync_head:
    adrp x8, SYM_BSS_STATE
    add  x8, x8, :lo12:SYM_BSS_STATE
    stp  xzr, xzr, [x8, #0x08]   /* clear valid[0..1], hit[0..1] */
    str  wzr, [x8, #0x18]        /* clear mouse_hit */
    str  xzr, [x8, #0x38]        /* clear btn_active[0..1] */
    ldr  x27, [x20, #8]          /* original instruction @ 0x1f8d14 */
    b    SYM_SYNC_CONT

.global cave2_sync_hit
cave2_sync_hit:
    stp  x29, x30, [sp, #-16]!
    bl   SYM_GET_HIT

    ldr  w8, [x27, #32]          /* InputSourceType */

    /* Combine ALL hit targets: panel content, caption/drag bar, resize bar, isHit bit 0 */
    ldr  x9, [x22, #88]
    ldr  x10, [x22, #104]
    orr  x9, x9, x10
    ldr  x10, [x22, #112]
    orr  x9, x9, x10
    ldrb w10, [x22, #120]
    and  w10, w10, #1
    orr  x9, x9, x10
    cmp  x9, #0
    cset w10, ne                 /* w10 = hit (0 or 1) */

    adrp x11, SYM_BSS_STATE
    add  x11, x11, :lo12:SYM_BSS_STATE

    /* Mouse (0x40) */
    cmp  w8, #0x40
    b.ne 1f
    str  w10, [x11, #0x18]
    b    .Lc2_ret

1:  /* Controllers only: 0x02 -> slot 0, 0x04 -> slot 1; Hands (0x10/0x20) & HMD ignored */
    cmp  w8, #0x02
    b.eq .Lc2_ctrl
    cmp  w8, #0x04
    b.ne .Lc2_ret

.Lc2_ctrl:
    ldrb w13, [x21, #36]         /* aimPoseValid */
    cbz  w13, .Lc2_ret

    cmp  w8, #0x04
    cset w12, eq                 /* w12 = slot (0 for 0x02, 1 for 0x04) */

    /* Read Trigger click (+2948) OR Inner Grip value (+2908 > 0.35f) */
    ldrb w0, [x21, #2948]
    ldr  s0, [x21, #2908]
    ldr  s1, .Lconst_grip_th
    fcmp s0, s1
    cset w13, gt
    orr  w0, w0, w13
    add  x14, x11, #0x38
    str  w0, [x14, x12, lsl #2]  /* btn_active[slot] */

    mov  w13, #1
    add  x14, x11, #0x08
    str  w13, [x14, x12, lsl #2] /* valid[slot] = 1 */
    add  x14, x11, #0x10
    str  w10, [x14, x12, lsl #2] /* hit[slot] = hit */

    /* Check if gMainInputSource switched to this controller */
    adrp x14, SYM_MAIN_SRC
    ldr  x14, [x14, :lo12:SYM_MAIN_SRC]
    cmp  x14, x21
    b.ne 2f
    ldr  x15, [x11, #0x20]       /* prev_main_src */
    cmp  x14, x15
    b.eq 2f
    str  x14, [x11, #0x20]
    str  w12, [x11, #0x04]       /* last_active = slot */

2:  /* Compute pose pointer: x15 = &prev_pose[slot][0] */
    add  x15, x11, #0x40
    add  x15, x15, x12, lsl #5

    /* Load current aimPose (qx,qy,qz,qw @ +68..80, px,py,pz @ +84..92) */
    ldp  s0, s1, [x21, #68]
    ldp  s2, s3, [x21, #76]
    ldp  s4, s5, [x21, #84]
    ldr  s6, [x21, #92]

    add  x14, x11, #0x30
    ldr  w13, [x14, x12, lsl #2] /* has_prev[slot] */
    cbnz w13, 3f

    /* First frame for this controller: store pose & mark initialized */
    stp  s0, s1, [x15, #0]
    stp  s2, s3, [x15, #8]
    stp  s4, s5, [x15, #16]
    str  s6, [x15, #24]
    mov  w13, #1
    str  w13, [x14, x12, lsl #2]
    b    .Lc2_ret

3:  /* Load prev pose, then save new pose */
    ldp  s16, s17, [x15, #0]
    ldp  s18, s19, [x15, #8]
    ldp  s20, s21, [x15, #16]
    ldr  s22, [x15, #24]

    stp  s0, s1, [x15, #0]
    stp  s2, s3, [x15, #8]
    stp  s4, s5, [x15, #16]
    str  s6, [x15, #24]

    /* Quaternion sign alignment: if dot(q, prev_q) < 0, negate prev_q */
    fmul  s7, s0, s16
    fmadd s7, s1, s17, s7
    fmadd s7, s2, s18, s7
    fmadd s7, s3, s19, s7
    fcmp  s7, #0.0
    b.ge  4f
    fneg  s16, s16
    fneg  s17, s17
    fneg  s18, s18
    fneg  s19, s19

4:  /* dq = |q - prev_q| (L1) */
    fsub  s0, s0, s16
    fabs  s0, s0
    fsub  s1, s1, s17
    fabs  s1, s1
    fsub  s2, s2, s18
    fabs  s2, s2
    fsub  s3, s3, s19
    fabs  s3, s3
    fadd  s0, s0, s1
    fadd  s2, s2, s3
    fadd  s0, s0, s2

    /* dp = |p - prev_p| (L1), weighted x2 */
    fsub  s4, s4, s20
    fabs  s4, s4
    fsub  s5, s5, s21
    fabs  s5, s5
    fsub  s6, s6, s22
    fabs  s6, s6
    fadd  s4, s4, s5
    fadd  s4, s4, s6
    fadd  s4, s4, s4             /* 2.0 * dp */
    fadd  s0, s0, s4             /* delta = dq + 2*dp */

    /* ema[slot] = ema[slot] * 0.85 + delta */
    add  x14, x11, #0x28
    ldr  s1, [x14, x12, lsl #2]
    ldr  s2, .Lconst_decay
    fmadd s1, s1, s2, s0
    str  s1, [x14, x12, lsl #2]

.Lc2_ret:
    ldp  x29, x30, [sp], #16
    ret

.global cave3_sync_end
cave3_sync_end:
    stp  x29, x30, [sp, #-16]!

    adrp x8, SYM_BSS_STATE
    add  x8, x8, :lo12:SYM_BSS_STATE

    ldp  w9, w10, [x8, #0x08]    /* w9=valid[0], w10=valid[1] */
    ldp  w11, w12, [x8, #0x10]   /* w11=hit[0], w12=hit[1] */
    ldr  w13, [x8, #0x18]        /* w13=mouse_hit */
    ldr  w14, [x8, #0x04]        /* w14=last_active */
    ldp  s0, s1, [x8, #0x28]     /* s0=ema[0], s1=ema[1] */

    /* 1) Update last_active controller by motion EMA */
    ldr  s2, .Lconst_min_act     /* 0.015f */
    ldr  s3, .Lconst_ratio       /* 1.35f */

    cbz  w9, 1f
    fcmp s0, s2
    b.le 1f
    fmul s4, s1, s3
    fcmp s0, s4
    b.le 1f
    mov  w14, #0
    b    2f
1:
    cbz  w10, 2f
    fcmp s1, s2
    b.le 2f
    fmul s4, s0, s3
    fcmp s1, s4
    b.le 2f
    mov  w14, #1
2:
    str  w14, [x8, #0x04]

    /* 2) Inner-grip & trigger release debounce (btn_hold @ +0x84):
     *    While either trigger or inner grip is held (or within 14 frames ~155ms after release),
     *    freeze current hover_focus (in BOTH VR and 2D!) to stop bounce & mid-grip stealing. */
    ldp  w16, w17, [x8, #0x38]   /* btn_active[0], btn_active[1] */
    orr  w16, w16, w17
    cbz  w16, .Lc3_btn_dec
    mov  w16, #14
    str  w16, [x8, #0x84]        /* btn_hold = 14 */
    str  wzr, [x8, #0x1C]        /* stable_cnt = 0 */
    b    .Lc3_done
.Lc3_btn_dec:
    ldr  w16, [x8, #0x84]
    cbz  w16, .Lc3_cool
    sub  w16, w16, #1
    str  w16, [x8, #0x84]
    str  wzr, [x8, #0x1C]
    b    .Lc3_done

    /* 3) Post-switch cooldown (@ +0x80): prevents rapid ping-pong on ray-mapping shift */
.Lc3_cool:
    ldr  w16, [x8, #0x80]
    cbz  w16, .Lc3_eval
    sub  w16, w16, #1
    str  w16, [x8, #0x80]
    str  wzr, [x8, #0x1C]
    b    .Lc3_done

    /* 4) Compute raw_focus (w15) */
.Lc3_eval:
    cbnz w13, .Lc3_raw_yes       /* mouse hit */
    cbz  w9, .Lc3_only1
    cbz  w10, .Lc3_only0
    cmp  w11, w12
    b.eq .Lc3_same
    cmp  w14, #0
    csel w15, w11, w12, eq       /* disagree -> hit[last_active] */
    b    .Lc3_debounce
.Lc3_same:
    mov  w15, w11
    b    .Lc3_debounce
.Lc3_only0:
    mov  w15, w11
    b    .Lc3_debounce
.Lc3_only1:
    cbz  w10, .Lc3_raw_no        /* bare hands / no controller -> 0 */
    mov  w15, w12
    b    .Lc3_debounce
.Lc3_raw_yes:
    mov  w15, #1
    b    .Lc3_debounce
.Lc3_raw_no:
    mov  w15, #0

    /* 5) Bidirectional entry/exit debounce:
     *    0->1 requires 10 consecutive frames (~110ms)
     *    1->0 requires 14 consecutive frames (~155ms) */
.Lc3_debounce:
    ldr  w16, [x8, #0x00]        /* cur hover_focus */
    cmp  w15, w16
    b.ne .Lc3_want_flip
    str  wzr, [x8, #0x1C]        /* matches current state -> stable_cnt = 0 */
    b    .Lc3_done

.Lc3_want_flip:
    ldr  w17, [x8, #0x1C]        /* stable_cnt */
    add  w17, w17, #1
    ldp  w16, w13, [x8, #0x88]   /* w16=cfg_enter (0->1), w13=cfg_exit (1->0) */
    cmp  w15, #0
    csel w16, w13, w16, eq
    cmp  w17, w16
    b.lt .Lc3_save_cnt
    /* Commit state transition + arm configurable cooldown */
    str  w15, [x8, #0x00]
    str  wzr, [x8, #0x1C]
    ldr  w16, [x8, #0x90]        /* cfg_cool */
    str  w16, [x8, #0x80]
    b    .Lc3_done
.Lc3_save_cnt:
    str  w17, [x8, #0x1C]

.Lc3_done:
    bl   SYM_TRACE_END
    ldp  x29, x30, [sp], #16
    ret

.global cave4_render_foc
cave4_render_foc:
    ldr  w8, [x23, #24]
    cmp  w8, #0xbba
    b.ne .Lc4_focus
    adrp x8, SYM_BSS_STATE
    ldr  w8, [x8, :lo12:SYM_BSS_STATE]
    cbz  w8, .Lc4_skip
.Lc4_focus:
    mov  w8, #1
    str  w8, [sp, #68]
    ldr  w8, [x23]
    str  w8, [sp, #84]
.Lc4_skip:
    b    SYM_FOC_RET

.align 2
.Lconst_decay:   .float 0.85
.Lconst_min_act: .float 0.015
.Lconst_ratio:   .float 1.35
.Lconst_grip_th: .float 0.35
"""

with tempfile.TemporaryDirectory() as td:
    s_path = os.path.join(td, "caves.S")
    o_path = os.path.join(td, "caves.o")
    elf_path = os.path.join(td, "caves.elf")
    bin_path = os.path.join(td, "caves.bin")
    with open(s_path, "w") as f:
        f.write(ASM)
    subprocess.check_call(["aarch64-linux-gnu-as", "-o", o_path, s_path])
    subprocess.check_call([
        "aarch64-linux-gnu-ld", "-Ttext=0x387c40",
        "--defsym=SYM_BSS_STATE=0x433f00",
        "--defsym=SYM_MAIN_SRC=0x3a2490",
        "--defsym=SYM_SYNC_CONT=0x1f8d18",
        "--defsym=SYM_GET_HIT=0x37f0e0",
        "--defsym=SYM_TRACE_END=0x37f0f0",
        "--defsym=SYM_FOC_RET=0x21d0e4",
        "-e", "cave1_sync_head",
        "-o", elf_path, o_path
    ])
    subprocess.check_call(["aarch64-linux-gnu-objcopy", "-O", "binary", "-j", ".text", elf_path, bin_path])

    syms = {}
    nm_out = subprocess.check_output(["aarch64-linux-gnu-nm", elf_path], text=True)
    for line in nm_out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2].startswith("cave"):
            syms[parts[2]] = int(parts[0], 16)

    blob = open(bin_path, "rb").read()
    assert len(blob) <= 960, f"Cave blob too big: {len(blob)} > 960"
    assert len(blob) % 4 == 0
    words = struct.unpack(f"<{len(blob)//4}I", blob)

    print(f"Assembled OK: {len(blob)} bytes ({len(words)} words) / 960 bytes available")
    for k, v in sorted(syms.items()):
        print(f"  {k} = 0x{v:x}")

    hdr_path = "/home/steve/文档/pico/pico-vr-multiwindow/hover_caves.h"
    with open(hdr_path, "w") as f:
        f.write("/* Auto-generated by gen_hover_caves.py — do not edit manually */\n")
        f.write("#pragma once\n#include <stdint.h>\n\n")
        f.write("#define VADDR_CAVE_BASE 0x387c40ULL\n")
        for k, v in sorted(syms.items()):
            f.write(f"#define VADDR_{k.upper()} 0x{v:x}ULL\n")
        f.write(f"#define HOVER_CAVE_WORDS {len(words)}\n\n")
        f.write("static const uint32_t HOVER_CAVE_BLOB[HOVER_CAVE_WORDS] = {\n")
        for i in range(0, len(words), 4):
            chunk = ", ".join(f"0x{w:08x}U" for w in words[i:i+4])
            f.write(f"    {chunk},\n")
        f.write("};\n")
    print("Wrote", hdr_path)
