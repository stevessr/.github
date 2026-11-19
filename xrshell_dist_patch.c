#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ptrace.h>
#include <sys/wait.h>
#include <unistd.h>
#include "hover_caves.h"

/*
 * libxrshell.so (mapped inside XRShell.apk, r-xp segment vaddr base 0x1b0000):
 *
 * 1) Distance patch (CaptionBarInteractor::onRockValueChanged):
 *   vaddr 0x2362e8 (off 0x862e8): 94052cd6  bl checkAttachedPanelMoveOutScreenRegion
 *   vaddr 0x2362ec (off 0x862ec): 3607f820  tbz w0, #0, 0x2361f0  -->  d503201f (nop)
 *
 * 2) Focus modes (OpenXRLoader::renderFrame @ vaddr 0x21d0c8, off 0x6d0c8):
 *   - always2d (0): original 7 insns (any visible 3002 panel grabs OpenXR session focus)
 *   - menu     (1): inline 7 insns (skip setSessionFocus(true) when windowType == 3002)
 *   - hover    (2): code caves @ vaddr 0x387d00..0x387d90 + BSS flag @ vaddr 0x433f00
 *                   syncInputHitInfo records whether ANY ray hit a panel (hitInfo.hitPanel != NULL);
 *                   renderFrame allows 3002 to grab OpenXR session focus ONLY while ray hits a panel!
 */
#define VADDR_TEXT_BASE 0x1b0000ULL
#define VADDR_BSS_FLAG  0x433f00ULL

#define VADDR_DIST_BL   0x2362e8ULL
#define VADDR_DIST_TBZ  0x2362ecULL
#define INSN_DIST_BL    0x94052cd6U
#define INSN_DIST_TBZ   0x3607f820U
#define INSN_NOP        0xd503201fU

#define VADDR_SYNC_HEAD 0x1f8d14ULL
#define INSN_SYNC_HEAD  0xf940069bU /* ldr x27, [x20, #8] */

#define VADDR_SYNC_BL   0x1f8f2cULL
#define VADDR_GET_HIT   0x37f0e0ULL
#define INSN_SYNC_BL    0x9406186dU /* bl getRayPanelHitPoint@plt */

#define VADDR_SYNC_END  0x1f8f78ULL
#define INSN_SYNC_END   0x9406185eU /* bl ___xrShellTraceEnd()@plt */

#define VADDR_FOC_HDR   0x21d0c0ULL
#define VADDR_FOC_BODY  0x21d0c8ULL
#define VADDR_FOC_RET   0x21d0e4ULL
#define INSN_FOC_H0     0x394012e8U
#define INSN_FOC_H1     0x34000108U

static const uint32_t FOC_ORIG[7] = {
    0xb94002e8U, 0xb94057e9U, 0x6b08013fU, 0x1a89b109U,
    0x52800028U, 0xb90057e9U, 0xb90047e8U
};

static const uint32_t FOC_MENU[7] = {
    0xb9401ae8U, 0x712ee91fU, 0x540000a0U, 0x52800028U,
    0xb90047e8U, 0xb94002e8U, 0xb90057e8U
};

static uint32_t enc_adrp(uint64_t pc, uint64_t target, int reg) {
    int64_t dp = ((int64_t)(target & ~0xFFFULL) - (int64_t)(pc & ~0xFFFULL)) >> 12;
    uint32_t immlo = (uint32_t)(dp & 0x3);
    uint32_t immhi = (uint32_t)((dp >> 2) & 0x7FFFF);
    return 0x90000000U | (immlo << 29) | (immhi << 5) | (uint32_t)(reg & 0x1F);
}

static uint32_t enc_b(uint64_t pc, uint64_t target) {
    int32_t imm26 = (int32_t)(((int64_t)target - (int64_t)pc) >> 2) & 0x03FFFFFF;
    return 0x14000000U | (uint32_t)imm26;
}

static uint32_t enc_bl(uint64_t pc, uint64_t target) {
    int32_t imm26 = (int32_t)(((int64_t)target - (int64_t)pc) >> 2) & 0x03FFFFFF;
    return 0x94000000U | (uint32_t)imm26;
}

static int find_text_base(pid_t pid, uint64_t *out_base) {
    char path[64], mem_path[64];
    snprintf(path, sizeof(path), "/proc/%d/maps", pid);
    snprintf(mem_path, sizeof(mem_path), "/proc/%d/mem", pid);
    FILE *fp = fopen(path, "r");
    if (!fp) return -1;
    int mfd = open(mem_path, O_RDONLY);
    if (mfd < 0) { fclose(fp); return -1; }

    char line[512];
    int found = 0;
    uint64_t off_bl = VADDR_DIST_BL - VADDR_TEXT_BASE;
    while (fgets(line, sizeof(line), fp)) {
        if (!strstr(line, "XRShell.apk") && !strstr(line, "libxrshell.so")) continue;
        unsigned long long start = 0, end = 0;
        char perms[8] = {0};
        if (sscanf(line, "%llx-%llx %7s", &start, &end, perms) != 3) continue;
        if (perms[2] != 'x') continue;
        if (end - start <= off_bl + 8) continue;

        uint32_t insns[2] = {0, 0};
        if (pread(mfd, insns, sizeof(insns), (off_t)(start + off_bl)) == sizeof(insns)) {
            if (insns[0] == INSN_DIST_BL && (insns[1] == INSN_DIST_TBZ || insns[1] == INSN_NOP)) {
                *out_base = start;
                found = 1;
                break;
            }
        }
    }
    close(mfd);
    fclose(fp);
    return found ? 0 : -1;
}

static uint64_t va2addr(uint64_t base, uint64_t vaddr) {
    return base + (vaddr - VADDR_TEXT_BASE);
}

static int apply_writes(pid_t pid, int fd, int (*fn)(int fd, uint64_t base, int arg), uint64_t base, int arg) {
    if (ptrace(PTRACE_ATTACH, pid, NULL, NULL) == 0) {
        waitpid(pid, NULL, 0);
    }
    int rc = fn(fd, base, arg);
    ptrace(PTRACE_DETACH, pid, NULL, NULL);
    return rc;
}

static int do_dist_write(int fd, uint64_t base, int on) {
    uint32_t want = on ? INSN_NOP : INSN_DIST_TBZ;
    return pwrite(fd, &want, sizeof(want), (off_t)va2addr(base, VADDR_DIST_TBZ)) == sizeof(want) ? 0 : -1;
}

static void calc_delay_cfg(int delay_ms, uint32_t cfg[3]) {
    if (delay_ms < 0) delay_ms = 0;
    if (delay_ms > 2000) delay_ms = 2000;
    uint32_t enter_f = (uint32_t)((delay_ms * 90 + 500) / 1000);
    if (enter_f < 1) enter_f = 1;
    uint32_t exit_f = enter_f + 5;
    uint32_t cool_f = (enter_f < 20) ? 20 : enter_f;
    cfg[0] = enter_f;
    cfg[1] = exit_f;
    cfg[2] = cool_f;
}

static int g_hover_delay_ms = 250;

/* arg: 0=always2d, 1=menu, 2=hover (active-controller priority, hands excluded) */
static int do_focus_write(int fd, uint64_t base, int mode) {
    if (mode == 2) {
        uint8_t zeros[160] = {0};
        uint32_t cfg[3];
        calc_delay_cfg(g_hover_delay_ms, cfg);
        uint32_t b_c1 = enc_b(VADDR_SYNC_HEAD, VADDR_CAVE1_SYNC_HEAD);
        uint32_t bl_c2 = enc_bl(VADDR_SYNC_BL, VADDR_CAVE2_SYNC_HIT);
        uint32_t bl_c3 = enc_bl(VADDR_SYNC_END, VADDR_CAVE3_SYNC_END);
        uint32_t foc_jmp[7] = {
            enc_b(VADDR_FOC_BODY, VADDR_CAVE4_RENDER_FOC),
            INSN_NOP, INSN_NOP, INSN_NOP, INSN_NOP, INSN_NOP, INSN_NOP
        };
        if (pwrite(fd, zeros, sizeof(zeros), (off_t)va2addr(base, VADDR_BSS_FLAG)) != sizeof(zeros)) return -1;
        if (pwrite(fd, cfg, sizeof(cfg), (off_t)va2addr(base, VADDR_BSS_FLAG + 0x88)) != sizeof(cfg)) return -1;
        if (pwrite(fd, HOVER_CAVE_BLOB, sizeof(HOVER_CAVE_BLOB), (off_t)va2addr(base, VADDR_CAVE_BASE)) != sizeof(HOVER_CAVE_BLOB)) return -1;
        if (pwrite(fd, &b_c1, sizeof(b_c1), (off_t)va2addr(base, VADDR_SYNC_HEAD)) != sizeof(b_c1)) return -1;
        if (pwrite(fd, &bl_c2, sizeof(bl_c2), (off_t)va2addr(base, VADDR_SYNC_BL)) != sizeof(bl_c2)) return -1;
        if (pwrite(fd, &bl_c3, sizeof(bl_c3), (off_t)va2addr(base, VADDR_SYNC_END)) != sizeof(bl_c3)) return -1;
        if (pwrite(fd, foc_jmp, sizeof(foc_jmp), (off_t)va2addr(base, VADDR_FOC_BODY)) != sizeof(foc_jmp)) return -1;
        return 0;
    } else {
        /* Restore syncInputHitInfo hooks first */
        uint32_t orig_h = INSN_SYNC_HEAD;
        uint32_t orig_bl = INSN_SYNC_BL;
        uint32_t orig_end = INSN_SYNC_END;
        const uint32_t *body = (mode == 1) ? FOC_MENU : FOC_ORIG;
        if (pwrite(fd, &orig_h, sizeof(orig_h), (off_t)va2addr(base, VADDR_SYNC_HEAD)) != sizeof(orig_h)) return -1;
        if (pwrite(fd, &orig_bl, sizeof(orig_bl), (off_t)va2addr(base, VADDR_SYNC_BL)) != sizeof(orig_bl)) return -1;
        if (pwrite(fd, &orig_end, sizeof(orig_end), (off_t)va2addr(base, VADDR_SYNC_END)) != sizeof(orig_end)) return -1;
        if (pwrite(fd, body, sizeof(FOC_ORIG), (off_t)va2addr(base, VADDR_FOC_BODY)) != sizeof(FOC_ORIG)) return -1;
        return 0;
    }
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s <pid> <status|patch|restore|dist_patch|dist_restore|focus_patch|focus_hover|focus_restore>\n", argv[0]);
        return 2;
    }
    pid_t pid = (pid_t)atoi(argv[1]);
    const char *mode = argv[2];
    uint64_t base = 0;
    if (find_text_base(pid, &base) != 0) {
        fprintf(stderr, "libxrshell.so text segment not found in pid %d\n", pid);
        return 1;
    }

    char mem_path[64];
    snprintf(mem_path, sizeof(mem_path), "/proc/%d/mem", pid);
    int fd = open(mem_path, strcmp(mode, "status") == 0 ? O_RDONLY : O_RDWR);
    if (fd < 0) { perror("open mem"); return 1; }

    uint32_t dist_cur = 0, foc_hdr[2] = {0}, foc_cur[7] = {0};
    if (pread(fd, &dist_cur, sizeof(dist_cur), (off_t)va2addr(base, VADDR_DIST_TBZ)) != sizeof(dist_cur) ||
        pread(fd, foc_hdr, sizeof(foc_hdr), (off_t)va2addr(base, VADDR_FOC_HDR)) != sizeof(foc_hdr) ||
        pread(fd, foc_cur, sizeof(foc_cur), (off_t)va2addr(base, VADDR_FOC_BODY)) != sizeof(foc_cur)) {
        perror("pread"); close(fd); return 1;
    }

    int dist_on = (dist_cur == INSN_NOP);
    int foc_state = 0; /* 0=always2d, 1=menu, 2=hover */
    if (foc_hdr[0] == INSN_FOC_H0 && foc_hdr[1] == INSN_FOC_H1) {
        if (memcmp(foc_cur, FOC_MENU, sizeof(FOC_MENU)) == 0) foc_state = 1;
        else if (foc_cur[0] == enc_b(VADDR_FOC_BODY, VADDR_CAVE4_RENDER_FOC)) foc_state = 2;
    }

    if (strcmp(mode, "status") == 0) {
        printf("xrshell_dist_patch=%d\n", dist_on);
        printf("xrshell_focus_patch=%d\n", foc_state);
        close(fd);
        return 0;
    }
    if (strcmp(mode, "dump") == 0) {
        uint32_t st[40] = {0};
        float ema[2] = {0, 0};
        if (pread(fd, st, sizeof(st), (off_t)va2addr(base, VADDR_BSS_FLAG)) == sizeof(st)) {
            memcpy(ema, &st[10], sizeof(ema));
            printf("hover_focus=%u last_active=%u valid=[%u,%u] hit=[%u,%u] mouse=%u stable=%u btn=[%u,%u] cool=%u bhold=%u cfg=[%u,%u,%u] ema=[%.4f,%.4f]\n",
                   st[0], st[1], st[2], st[3], st[4], st[5], st[6], st[7], st[14], st[15], st[32], st[33], st[34], st[35], st[36], ema[0], ema[1]);
        }
        close(fd);
        return 0;
    }
    if (strcmp(mode, "hover_delay") == 0) {
        int ms = (argc >= 4) ? atoi(argv[3]) : 250;
        uint32_t cfg[3];
        calc_delay_cfg(ms, cfg);
        int ok = (pwrite(fd, cfg, sizeof(cfg), (off_t)va2addr(base, VADDR_BSS_FLAG + 0x88)) == sizeof(cfg));
        close(fd);
        return ok ? 0 : 1;
    }

    int rc = 0;
    if (strcmp(mode, "patch") == 0) {
        rc |= apply_writes(pid, fd, do_dist_write, base, 1);
        rc |= apply_writes(pid, fd, do_focus_write, base, 1);
    } else if (strcmp(mode, "restore") == 0) {
        rc |= apply_writes(pid, fd, do_dist_write, base, 0);
        rc |= apply_writes(pid, fd, do_focus_write, base, 0);
    } else if (strcmp(mode, "dist_patch") == 0) {
        rc |= apply_writes(pid, fd, do_dist_write, base, 1);
    } else if (strcmp(mode, "dist_restore") == 0) {
        rc |= apply_writes(pid, fd, do_dist_write, base, 0);
    } else if (strcmp(mode, "focus_patch") == 0) {
        rc |= apply_writes(pid, fd, do_focus_write, base, 1);
    } else if (strcmp(mode, "focus_hover") == 0) {
        if (argc >= 4) g_hover_delay_ms = atoi(argv[3]);
        rc |= apply_writes(pid, fd, do_focus_write, base, 2);
    } else if (strcmp(mode, "focus_restore") == 0) {
        rc |= apply_writes(pid, fd, do_focus_write, base, 0);
    } else {
        fprintf(stderr, "unknown mode: %s\n", mode);
        rc = 2;
    }

    close(fd);
    return rc;
}
