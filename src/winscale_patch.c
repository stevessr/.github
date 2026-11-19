#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ptrace.h>
#include <sys/wait.h>
#include <unistd.h>

/*
 * libxrshell.so virtual addresses (from ELF base 0x0):
 *   .rodata Constants::kMaxAppScreenRadius   @ 0x155498 (float, stock 12.0f)
 *   .rodata Constants::kMaxFreePanelDistance @ 0x1554a0 (float, stock 12.0f)
 *   .rodata Constants::kMinFreePanelDistance @ 0x1554a4 (float, stock 0.5f)
 *   .rodata kCustomScaleMaxMinSize template  @ 0x1555d8 (int32[6]: {1600, 900, 2400, 1350, 900, 850})
 *   .text   r-xp base                        @ 0x1b0000
 *   .text   xCamera::setFarPlan mov w8       @ 0x250468 (stock 0x52a85908 = 100.0f, patch 0x52a88f48 = 1000.0f)
 *   .bss    Constants::kCustomScaleMaxMinSize@ 0x3a2460 (std::vector<int32_t>: __begin_, __end_, __cap_)
 */

#define VADDR_TEXT_BASE        0x1b0000ULL
#define VADDR_MAX_SCREEN_RAD   0x155498ULL
#define VADDR_MAX_FREE_DIST    0x1554a0ULL
#define VADDR_MIN_FREE_DIST    0x1554a4ULL
#define VADDR_SCALE_TMPL       0x1555d8ULL
#define VADDR_FAR_PLANE_INSN   0x250468ULL
#define VADDR_SCALE_VEC_BSS    0x3a2460ULL

#define INSN_FAR_100F          0x52a85908U
#define INSN_FAR_1000F         0x52a88f48U

#define STOCK_DIST             12.0f
#define STOCK_MAX_W            2400
#define STOCK_MAX_H            1350
#define UNTAG(p)               ((p) & 0x00FFFFFFFFFFFFFFULL)

static int find_elf_base(pid_t pid, uint64_t *out_base) {
    char maps_path[64], mem_path[64];
    snprintf(maps_path, sizeof(maps_path), "/proc/%d/maps", pid);
    snprintf(mem_path, sizeof(mem_path), "/proc/%d/mem", pid);

    FILE *fp = fopen(maps_path, "r");
    if (!fp) return -1;
    int mfd = open(mem_path, O_RDONLY);
    if (mfd < 0) {
        fclose(fp);
        return -1;
    }

    char line[512];
    int found = 0;
    uint64_t off_far = VADDR_FAR_PLANE_INSN - VADDR_TEXT_BASE;

    while (fgets(line, sizeof(line), fp)) {
        if (!strstr(line, "XRShell.apk") && !strstr(line, "libxrshell.so")) continue;
        unsigned long long start = 0, end = 0;
        char perms[8] = {0};
        if (sscanf(line, "%llx-%llx %7s", &start, &end, perms) != 3) continue;
        if (perms[2] != 'x') continue;
        if (start < VADDR_TEXT_BASE) continue;
        if (end - start <= off_far + 4) continue;

        uint32_t insn = 0;
        if (pread(mfd, &insn, sizeof(insn), (off_t)(start + off_far)) != sizeof(insn)) continue;
        if (insn != INSN_FAR_100F && insn != INSN_FAR_1000F) continue;

        uint64_t base = start - VADDR_TEXT_BASE;
        float min_dist = 0.0f;
        int32_t def_wh[2] = {0, 0};
        if (pread(mfd, &min_dist, sizeof(min_dist), (off_t)(base + VADDR_MIN_FREE_DIST)) == sizeof(min_dist) &&
            pread(mfd, def_wh, sizeof(def_wh), (off_t)(base + VADDR_SCALE_TMPL)) == sizeof(def_wh)) {
            if (min_dist > 0.49f && min_dist < 0.51f && def_wh[0] == 1600 && def_wh[1] == 900) {
                *out_base = base;
                found = 1;
                break;
            }
        }
    }

    close(mfd);
    fclose(fp);
    return found ? 0 : -1;
}

static int read_state(int fd, uint64_t base, float *max_dist, float *max_rad,
                      uint32_t *far_insn, int32_t *vec_wh, int32_t *ro_wh) {
    if (pread(fd, max_dist, sizeof(*max_dist), (off_t)(base + VADDR_MAX_FREE_DIST)) != sizeof(*max_dist)) return -1;
    if (pread(fd, max_rad, sizeof(*max_rad), (off_t)(base + VADDR_MAX_SCREEN_RAD)) != sizeof(*max_rad)) return -1;
    if (pread(fd, far_insn, sizeof(*far_insn), (off_t)(base + VADDR_FAR_PLANE_INSN)) != sizeof(*far_insn)) return -1;
    if (pread(fd, ro_wh, 8, (off_t)(base + VADDR_SCALE_TMPL + 8)) != 8) return -1;

    uint64_t vec_ptrs[2] = {0, 0};
    if (pread(fd, vec_ptrs, sizeof(vec_ptrs), (off_t)(base + VADDR_SCALE_VEC_BSS)) == sizeof(vec_ptrs) &&
        UNTAG(vec_ptrs[0]) != 0 && (UNTAG(vec_ptrs[1]) - UNTAG(vec_ptrs[0])) == 24) {
        if (pread(fd, vec_wh, 8, (off_t)(UNTAG(vec_ptrs[0]) + 8)) != 8) {
            vec_wh[0] = -1;
            vec_wh[1] = -1;
        }
    } else {
        vec_wh[0] = -1;
        vec_wh[1] = -1;
    }
    return 0;
}

static int apply_patch(pid_t pid, int fd, uint64_t base, float max_dist, int32_t max_w, int32_t max_h, uint32_t far_insn) {
    int attached = 0;
    if (ptrace(PTRACE_ATTACH, pid, NULL, NULL) == 0) {
        waitpid(pid, NULL, 0);
        attached = 1;
    }

    int rc = 0;
    if (pwrite(fd, &max_dist, sizeof(max_dist), (off_t)(base + VADDR_MAX_FREE_DIST)) != sizeof(max_dist)) { perror("pwrite max_free_dist"); rc = -1; }
    if (pwrite(fd, &max_dist, sizeof(max_dist), (off_t)(base + VADDR_MAX_SCREEN_RAD)) != sizeof(max_dist)) { perror("pwrite max_screen_rad"); rc = -1; }
    if (pwrite(fd, &far_insn, sizeof(far_insn), (off_t)(base + VADDR_FAR_PLANE_INSN)) != sizeof(far_insn)) { perror("pwrite far_insn"); rc = -1; }

    int32_t wh[2] = {max_w, max_h};
    if (pwrite(fd, wh, sizeof(wh), (off_t)(base + VADDR_SCALE_TMPL + 8)) != sizeof(wh)) { perror("pwrite ro_wh"); rc = -1; }

    uint64_t vec_ptrs[2] = {0, 0};
    if (pread(fd, vec_ptrs, sizeof(vec_ptrs), (off_t)(base + VADDR_SCALE_VEC_BSS)) == sizeof(vec_ptrs) &&
        UNTAG(vec_ptrs[0]) != 0 && (UNTAG(vec_ptrs[1]) - UNTAG(vec_ptrs[0])) == 24) {
        if (pwrite(fd, wh, sizeof(wh), (off_t)(UNTAG(vec_ptrs[0]) + 8)) != sizeof(wh)) { perror("pwrite vec_wh"); rc = -1; }
    }

    if (attached) {
        ptrace(PTRACE_DETACH, pid, NULL, NULL);
    }
    return rc;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s <pid> <status|apply <max_dist> <max_w> <max_h>|reset>\n", argv[0]);
        return 2;
    }

    pid_t pid = (pid_t)atoi(argv[1]);
    const char *cmd = argv[2];

    uint64_t base = 0;
    if (find_elf_base(pid, &base) != 0) {
        fprintf(stderr, "libxrshell.so not found in pid %d\n", pid);
        return 1;
    }

    char mem_path[64];
    snprintf(mem_path, sizeof(mem_path), "/proc/%d/mem", pid);
    int is_status = (strcmp(cmd, "status") == 0);
    int fd = open(mem_path, is_status ? O_RDONLY : O_RDWR);
    if (fd < 0) {
        perror("open mem");
        return 1;
    }

    if (is_status) {
        float max_dist = 0, max_rad = 0;
        uint32_t far_insn = 0;
        int32_t vec_wh[2] = {0, 0}, ro_wh[2] = {0, 0};
        if (read_state(fd, base, &max_dist, &max_rad, &far_insn, vec_wh, ro_wh) != 0) {
            perror("pread");
            close(fd);
            return 1;
        }
        int far_plane = (far_insn == INSN_FAR_1000F) ? 1000 : (far_insn == INSN_FAR_100F ? 100 : -1);
        printf("elf_base=0x%llx\n", (unsigned long long)base);
        printf("max_free_dist=%.1f\n", max_dist);
        printf("max_screen_radius=%.1f\n", max_rad);
        printf("far_plane=%d\n", far_plane);
        printf("max_scale_w=%d\n", vec_wh[0] > 0 ? vec_wh[0] : ro_wh[0]);
        printf("max_scale_h=%d\n", vec_wh[1] > 0 ? vec_wh[1] : ro_wh[1]);
        printf("ro_max_w=%d\n", ro_wh[0]);
        printf("ro_max_h=%d\n", ro_wh[1]);
        close(fd);
        return 0;
    }

    int rc = 0;
    if (strcmp(cmd, "apply") == 0) {
        if (argc < 6) {
            fprintf(stderr, "usage: %s <pid> apply <max_dist> <max_w> <max_h>\n", argv[0]);
            close(fd);
            return 2;
        }
        float max_dist = strtof(argv[3], NULL);
        int32_t max_w = (int32_t)atoi(argv[4]);
        int32_t max_h = (int32_t)atoi(argv[5]);
        if (max_dist < 12.0f) max_dist = 12.0f;
        if (max_dist > 500.0f) max_dist = 500.0f;
        if (max_w < 2400) max_w = 2400;
        if (max_w > 15360) max_w = 15360;
        if (max_h < 1350) max_h = 1350;
        if (max_h > 8640) max_h = 8640;
        rc = apply_patch(pid, fd, base, max_dist, max_w, max_h, INSN_FAR_1000F);
    } else if (strcmp(cmd, "reset") == 0) {
        rc = apply_patch(pid, fd, base, STOCK_DIST, STOCK_MAX_W, STOCK_MAX_H, INSN_FAR_100F);
    } else {
        fprintf(stderr, "unknown cmd: %s\n", cmd);
        rc = 2;
    }

    close(fd);
    return rc == 0 ? 0 : 1;
}
