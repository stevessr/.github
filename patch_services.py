#!/usr/bin/env python3
"""Patch PICO 4 Ultra services.jar (classes2.dex) to allow multiple 2D windows in VR games."""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
APKTOOL = os.path.join(REPO, "youtube-vr-repair/tools/apktool.jar")
ZIPALIGN = "/opt/android-sdk/build-tools/37.0.0/zipalign"
SRC_JAR = os.path.join(ROOT, "research/services.jar")
OUT_JAR = os.path.join(ROOT, "module/system/framework/services.jar")

HELPER_SMALI = """
.method private static isPicoVrMultiWindowEnabled()Z
    .locals 3

    :try_start_0
    invoke-static {}, Lcom/android/server/scenesmanager/AppManagerService;->getInstance()Lcom/android/server/scenesmanager/AppManagerService;

    move-result-object v0

    if-eqz v0, :cond_pico_mw_true

    invoke-virtual {v0}, Lcom/android/server/scenesmanager/AppManagerService;->getContext()Landroid/content/Context;

    move-result-object v0

    if-eqz v0, :cond_pico_mw_true

    invoke-virtual {v0}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v0

    const-string v1, "pico_vr_multiwindow"

    const/4 v2, 0x1

    invoke-static {v0, v1, v2}, Landroid/provider/Settings$Global;->getInt(Landroid/content/ContentResolver;Ljava/lang/String;I)I

    move-result v0

    if-eqz v0, :cond_pico_mw_false

    return v2

    :cond_pico_mw_false
    const/4 v0, 0x0

    return v0
    :try_end_0
    .catch Ljava/lang/Throwable; {:try_start_0 .. :try_end_0} :catch_pico_mw

    :catch_pico_mw
    :cond_pico_mw_true
    const/4 v0, 0x1

    return v0
.end method
"""


def patch_root_app_container(smali_path: str) -> None:
    with open(smali_path, "r", encoding="utf-8") as f:
        text = f.read()

    # Patch 1: checkAllowStart2dAppInNearStack -> return false when enabled
    anchor1 = """    const/16 v1, 0xbba

    if-eq p1, v1, :cond_1

    return v0

    .line 2037
    :cond_1"""
    repl1 = """    const/16 v1, 0xbba

    if-eq p1, v1, :cond_1

    return v0

    .line 2037
    :cond_1
    invoke-static {}, Lcom/android/server/scenesmanager/RootAppContainer;->isPicoVrMultiWindowEnabled()Z

    move-result p1

    if-eqz p1, :cond_pico_mw_near_orig

    return v0

    :cond_pico_mw_near_orig"""
    assert text.count(anchor1) == 1, f"anchor1 count={text.count(anchor1)}"
    text = text.replace(anchor1, repl1, 1)

    # Patch 2: hideAllVisibleContainer -> ignore 3002 (0xbba) when i==8 and str=="top app changed"
    anchor2 = """    if-ne p2, v6, :cond_a

    const/16 v3, 0xfab

    .line 774
    invoke-virtual {p1, v3}, Lcom/android/server/scenesmanager/VisibleAppPanelScenes;->addIgnorePanelType(I)V

    .line 775
    invoke-virtual {p1, v10}, Lcom/android/server/scenesmanager/VisibleAppPanelScenes;->addIgnorePanelType(I)V

    .line 776
    invoke-virtual {p1, v9}, Lcom/android/server/scenesmanager/VisibleAppPanelScenes;->addIgnorePanelType(I)V

    .line 777
    invoke-virtual {p1, v8}, Lcom/android/server/scenesmanager/VisibleAppPanelScenes;->addIgnorePanelType(I)V

    goto :goto_1"""
    repl2 = """    if-ne p2, v6, :cond_a

    const/16 v3, 0xfab

    .line 774
    invoke-virtual {p1, v3}, Lcom/android/server/scenesmanager/VisibleAppPanelScenes;->addIgnorePanelType(I)V

    .line 775
    invoke-virtual {p1, v10}, Lcom/android/server/scenesmanager/VisibleAppPanelScenes;->addIgnorePanelType(I)V

    .line 776
    invoke-virtual {p1, v9}, Lcom/android/server/scenesmanager/VisibleAppPanelScenes;->addIgnorePanelType(I)V

    .line 777
    invoke-virtual {p1, v8}, Lcom/android/server/scenesmanager/VisibleAppPanelScenes;->addIgnorePanelType(I)V

    const-string v3, "top app changed"

    invoke-virtual {v3, p4}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-eqz v3, :cond_pico_mw_skip_ignore

    invoke-static {}, Lcom/android/server/scenesmanager/RootAppContainer;->isPicoVrMultiWindowEnabled()Z

    move-result v3

    if-eqz v3, :cond_pico_mw_skip_ignore

    const/16 v3, 0xbba

    invoke-virtual {p1, v3}, Lcom/android/server/scenesmanager/VisibleAppPanelScenes;->addIgnorePanelType(I)V

    :cond_pico_mw_skip_ignore
    goto :goto_1"""
    assert text.count(anchor2) == 1, f"anchor2 count={text.count(anchor2)}"
    text = text.replace(anchor2, repl2, 1)

    # Patch 3: lambda$handle3dEnvChanged$19 -> keep 3002 visible when switching 3D apps
    anchor3 = """    :cond_0
    const/4 p1, 0x0

    .line 1098
    invoke-virtual {p0, p2, p1}, Lcom/android/server/scenesmanager/RootAppContainer;->updateAppVisible(Lcom/android/server/scenesmanager/AppContainer;Z)V"""
    repl3 = """    :cond_0
    invoke-virtual {p2}, Lcom/android/server/scenesmanager/AppContainer;->getType()I

    move-result p1

    const/16 v0, 0xbba

    if-ne p1, v0, :cond_pico_mw_hide3d

    invoke-static {}, Lcom/android/server/scenesmanager/RootAppContainer;->isPicoVrMultiWindowEnabled()Z

    move-result p1

    if-eqz p1, :cond_pico_mw_hide3d

    return-void

    :cond_pico_mw_hide3d
    const/4 p1, 0x0

    .line 1098
    invoke-virtual {p0, p2, p1}, Lcom/android/server/scenesmanager/RootAppContainer;->updateAppVisible(Lcom/android/server/scenesmanager/AppContainer;Z)V"""
    assert text.count(anchor3) == 1, f"anchor3 count={text.count(anchor3)}"
    text = text.replace(anchor3, repl3, 1)

    # Patch 4: lambda$handleHomeAction$15 -> pressing Home inside VR game hides Dock, keeps 3002 2D apps
    anchor4 = """.method private synthetic lambda$handleHomeAction$15(Lcom/android/server/scenesmanager/AppContainer;)V
    .locals 1

    .line 698
    invoke-virtual {p1}, Lcom/android/server/scenesmanager/AppContainer;->ignoreHomeAction()Z

    move-result v0

    if-eqz v0, :cond_0

    return-void

    .line 699
    :cond_0"""
    repl4 = """.method private synthetic lambda$handleHomeAction$15(Lcom/android/server/scenesmanager/AppContainer;)V
    .locals 2

    .line 698
    invoke-virtual {p1}, Lcom/android/server/scenesmanager/AppContainer;->ignoreHomeAction()Z

    move-result v0

    if-eqz v0, :cond_0

    return-void

    .line 699
    :cond_0
    invoke-virtual {p1}, Lcom/android/server/scenesmanager/AppContainer;->getType()I

    move-result v0

    const/16 v1, 0xbba

    if-ne v0, v1, :cond_pico_mw_home_orig

    invoke-static {}, Lcom/android/server/scenesmanager/RootAppContainer;->isPicoVrMultiWindowEnabled()Z

    move-result v0

    if-eqz v0, :cond_pico_mw_home_orig

    return-void

    :cond_pico_mw_home_orig"""
    assert text.count(anchor4) == 1, f"anchor4 count={text.count(anchor4)}"
    text = text.replace(anchor4, repl4, 1)

    # Patch 5: remoteUpdatePanelVisible -> ignore hide (z=false) for 3002 when inside a 3D VR game (e.g. exiting menu)
    anchor5 = """    .line 2021
    invoke-virtual {p0, p1}, Lcom/android/server/scenesmanager/RootAppContainer;->resolveContainerByPanelId(I)Lcom/android/server/scenesmanager/AppContainer;

    move-result-object p1

    if-eqz p1, :cond_0

    .line 2023"""
    repl5 = """    .line 2021
    invoke-virtual {p0, p1}, Lcom/android/server/scenesmanager/RootAppContainer;->resolveContainerByPanelId(I)Lcom/android/server/scenesmanager/AppContainer;

    move-result-object p1

    if-eqz p1, :cond_0

    if-nez p2, :cond_pico_mw_remote_orig

    invoke-virtual {p1}, Lcom/android/server/scenesmanager/AppContainer;->getType()I

    move-result v0

    const/16 v1, 0xbba

    if-ne v0, v1, :cond_pico_mw_remote_orig

    iget-object v0, p0, Lcom/android/server/scenesmanager/RootAppContainer;->mTopTaskOnDefaultDisplay:Landroid/content/ComponentName;

    invoke-static {v0}, Lcom/android/server/scenesmanager/AppManagerUtils;->isHomeApp(Landroid/content/ComponentName;)Z

    move-result v0

    if-nez v0, :cond_pico_mw_remote_orig

    invoke-static {}, Lcom/android/server/scenesmanager/RootAppContainer;->isPicoVrMultiWindowEnabled()Z

    move-result v0

    if-eqz v0, :cond_pico_mw_remote_orig

    return-void

    :cond_pico_mw_remote_orig
    .line 2023"""
    assert text.count(anchor5) == 1, f"anchor5 count={text.count(anchor5)}"
    text = text.replace(anchor5, repl5, 1)

    # Append helper method
    text = text + "\n" + HELPER_SMALI

    with open(smali_path, "w", encoding="utf-8") as f:
        f.write(text)
    print("Patched RootAppContainer.smali successfully (5 hooks + helper).")


FORCE_RESIZE_HELPER = """
.method private static isPicoForceResizeEnabled()Z
    .locals 3

    :try_start_0
    invoke-static {}, Lcom/android/server/scenesmanager/AppManagerService;->getInstance()Lcom/android/server/scenesmanager/AppManagerService;

    move-result-object v0

    if-eqz v0, :cond_fr_true

    invoke-virtual {v0}, Lcom/android/server/scenesmanager/AppManagerService;->getContext()Landroid/content/Context;

    move-result-object v0

    if-eqz v0, :cond_fr_true

    invoke-virtual {v0}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v0

    const-string v1, "pico_vr_force_resize"

    const/4 v2, 0x1

    invoke-static {v0, v1, v2}, Landroid/provider/Settings$Global;->getInt(Landroid/content/ContentResolver;Ljava/lang/String;I)I

    move-result v0

    if-eqz v0, :cond_fr_false

    return v2

    :cond_fr_false
    const/4 v0, 0x0

    return v0
    :try_end_0
    .catch Ljava/lang/Throwable; {:try_start_0 .. :try_end_0} :catch_fr

    :catch_fr
    :cond_fr_true
    const/4 v0, 0x1

    return v0
.end method
"""


def patch_app_record(smali_path: str) -> None:
    with open(smali_path, "r", encoding="utf-8") as f:
        text = f.read()

    anchor = """.method private static isAppSupportResize(Ljava/lang/String;)Z
    .locals 1

    .line 97
    invoke-static {p0}, Landroid/text/TextUtils;->isEmpty(Ljava/lang/CharSequence;)Z

    move-result v0

    if-nez v0, :cond_1"""
    repl = """.method private static isAppSupportResize(Ljava/lang/String;)Z
    .locals 1

    .line 97
    invoke-static {p0}, Landroid/text/TextUtils;->isEmpty(Ljava/lang/CharSequence;)Z

    move-result v0

    if-nez v0, :cond_1

    invoke-static {}, Lcom/android/server/scenesmanager/AppRecord;->isPicoForceResizeEnabled()Z

    move-result v0

    if-eqz v0, :cond_pico_fr_orig

    const/4 p0, 0x1

    return p0

    :cond_pico_fr_orig"""
    assert text.count(anchor) == 1, f"AppRecord anchor count={text.count(anchor)}"
    text = text.replace(anchor, repl, 1) + "\n" + FORCE_RESIZE_HELPER

    with open(smali_path, "w", encoding="utf-8") as f:
        f.write(text)
    print("Patched AppRecord.smali successfully (isAppSupportResize + helper).")


OVERLAY_HELPER = """
.method private static resolvePicoOverlayDisplayId(Ljava/lang/String;)I
    .locals 5

    const/4 v0, 0x0

    :try_start_0
    invoke-static {}, Lcom/android/server/scenesmanager/AppManagerService;->getInstance()Lcom/android/server/scenesmanager/AppManagerService;

    move-result-object v1

    if-nez v1, :cond_ov_ctx

    return v0

    :cond_ov_ctx
    invoke-virtual {v1}, Lcom/android/server/scenesmanager/AppManagerService;->getContext()Landroid/content/Context;

    move-result-object v2

    if-eqz v2, :cond_ov_root

    invoke-virtual {v2}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v2

    const-string v3, "pico_vr_overlay_bridge"

    const/4 v4, 0x1

    invoke-static {v2, v3, v4}, Landroid/provider/Settings$Global;->getInt(Landroid/content/ContentResolver;Ljava/lang/String;I)I

    move-result v3

    if-nez v3, :cond_ov_pkg

    return v0

    :cond_ov_pkg
    if-eqz p0, :cond_ov_root

    const-string v3, "pico_vr_overlay_bridge_deny"

    invoke-static {v2, v3}, Landroid/provider/Settings$Global;->getString(Landroid/content/ContentResolver;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v2

    if-eqz v2, :cond_ov_root

    invoke-virtual {v2}, Ljava/lang/String;->isEmpty()Z

    move-result v3

    if-nez v3, :cond_ov_root

    new-instance v3, Ljava/lang/StringBuilder;

    invoke-direct {v3}, Ljava/lang/StringBuilder;-><init>()V

    const-string v4, ","

    invoke-virtual {v3, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v3, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v3, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v3}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v2, v3}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v2

    if-eqz v2, :cond_ov_root

    return v0

    :cond_ov_root
    invoke-virtual {v1}, Lcom/android/server/scenesmanager/AppManagerService;->getRootContainer()Lcom/android/server/scenesmanager/RootAppContainer;

    move-result-object v1

    if-nez v1, :cond_ov_stack

    return v0

    :cond_ov_stack
    invoke-virtual {v1}, Lcom/android/server/scenesmanager/RootAppContainer;->getFarAppStack()Lcom/android/server/scenesmanager/AppStack;

    move-result-object v1

    if-nez v1, :cond_ov_top

    return v0

    :cond_ov_top
    invoke-virtual {v1}, Lcom/android/server/scenesmanager/AppStack;->getTopVisibleApp()Lcom/android/server/scenesmanager/AppContainer;

    move-result-object v1

    if-nez v1, :cond_ov_did

    return v0

    :cond_ov_did
    invoke-virtual {v1}, Lcom/android/server/scenesmanager/AppContainer;->getDisplayId()I

    move-result v1

    if-lez v1, :cond_ov_zero

    return v1
    :try_end_0
    .catch Ljava/lang/Throwable; {:try_start_0 .. :try_end_0} :catch_ov

    :catch_ov
    :cond_ov_zero
    return v0
.end method
"""


def patch_ext_wms(smali_path: str) -> None:
    with open(smali_path, "r", encoding="utf-8") as f:
        text = f.read()

    anchor = """.method public onAddWindowStart(Landroid/view/WindowManager$LayoutParams;I)I
    .locals 2

    .line 387
    iget-object v0, p1, Landroid/view/WindowManager$LayoutParams;->panelAttributes:Landroid/view/PanelAttributes;

    .line 388
    iget-object p1, p1, Landroid/view/WindowManager$LayoutParams;->packageName:Ljava/lang/String;

    iput-object p1, v0, Landroid/view/PanelAttributes;->packageName:Ljava/lang/String;

    .line 390
    iget p1, v0, Landroid/view/PanelAttributes;->windowType:I

    if-nez p1, :cond_0

    return p2"""
    repl = """.method public onAddWindowStart(Landroid/view/WindowManager$LayoutParams;I)I
    .locals 3

    .line 387
    iget-object v0, p1, Landroid/view/WindowManager$LayoutParams;->panelAttributes:Landroid/view/PanelAttributes;

    iget v2, p1, Landroid/view/WindowManager$LayoutParams;->type:I

    .line 388
    iget-object p1, p1, Landroid/view/WindowManager$LayoutParams;->packageName:Ljava/lang/String;

    iput-object p1, v0, Landroid/view/PanelAttributes;->packageName:Ljava/lang/String;

    .line 390
    iget v1, v0, Landroid/view/PanelAttributes;->windowType:I

    if-nez v1, :cond_0

    if-nez p2, :cond_pico_ov_ret

    const/16 v1, 0x7f6

    if-ne v2, v1, :cond_pico_ov_ret

    invoke-static {p1}, Lcom/android/server/wm/ExtWindowManagerServiceImpl;->resolvePicoOverlayDisplayId(Ljava/lang/String;)I

    move-result v1

    if-lez v1, :cond_pico_ov_ret

    return v1

    :cond_pico_ov_ret
    return p2"""
    assert text.count(anchor) == 1, f"ExtWMS anchor count={text.count(anchor)}"
    text = text.replace(anchor, repl, 1) + "\n" + OVERLAY_HELPER

    with open(smali_path, "w", encoding="utf-8") as f:
        f.write(text)
    print("Patched ExtWindowManagerServiceImpl.smali successfully (TYPE_APPLICATION_OVERLAY redirect).")


def main() -> None:
    os.makedirs(os.path.dirname(OUT_JAR), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pico_mw_") as work:
        c2_dex = os.path.join(work, "classes2.dex")
        c2_apk = os.path.join(work, "c2.apk")
        decoded = os.path.join(work, "decoded")
        rebuilt_apk = os.path.join(work, "rebuilt.apk")
        patched_c2 = os.path.join(work, "classes2_patched.dex")
        c3_dex = os.path.join(work, "classes3.dex")
        c3_apk = os.path.join(work, "c3.apk")
        decoded3 = os.path.join(work, "decoded3")
        rebuilt_apk3 = os.path.join(work, "rebuilt3.apk")
        patched_c3 = os.path.join(work, "classes3_patched.dex")
        unaligned_jar = os.path.join(work, "services_unaligned.jar")

        with zipfile.ZipFile(SRC_JAR, "r") as zin:
            with open(c2_dex, "wb") as f:
                f.write(zin.read("classes2.dex"))
            with open(c3_dex, "wb") as f:
                f.write(zin.read("classes3.dex"))

        with zipfile.ZipFile(c2_apk, "w", compression=zipfile.ZIP_STORED) as z:
            z.write(c2_dex, "classes.dex")
        with zipfile.ZipFile(c3_apk, "w", compression=zipfile.ZIP_STORED) as z:
            z.write(c3_dex, "classes.dex")

        subprocess.run(["java", "-jar", APKTOOL, "d", "--no-res", "-f", "-o", decoded, c2_apk], check=True)
        smali_path = os.path.join(decoded, "smali/com/android/server/scenesmanager/RootAppContainer.smali")
        patch_root_app_container(smali_path)
        app_record_smali = os.path.join(decoded, "smali/com/android/server/scenesmanager/AppRecord.smali")
        patch_app_record(app_record_smali)

        subprocess.run(["java", "-jar", APKTOOL, "b", decoded, "-o", rebuilt_apk], check=True)
        with zipfile.ZipFile(rebuilt_apk, "r") as zr:
            with open(patched_c2, "wb") as f:
                f.write(zr.read("classes.dex"))

        subprocess.run(["java", "-jar", APKTOOL, "d", "--no-res", "-f", "-o", decoded3, c3_apk], check=True)
        ext_wms_smali = os.path.join(decoded3, "smali/com/android/server/wm/ExtWindowManagerServiceImpl.smali")
        patch_ext_wms(ext_wms_smali)

        subprocess.run(["java", "-jar", APKTOOL, "b", decoded3, "-o", rebuilt_apk3], check=True)
        with zipfile.ZipFile(rebuilt_apk3, "r") as zr:
            with open(patched_c3, "wb") as f:
                f.write(zr.read("classes.dex"))

        with zipfile.ZipFile(SRC_JAR, "r") as zin, zipfile.ZipFile(unaligned_jar, "w") as zout:
            for info in zin.infolist():
                if info.filename == "classes2.dex":
                    zi = zipfile.ZipInfo("classes2.dex", date_time=(2008, 1, 1, 0, 0, 0))
                    zi.compress_type = zipfile.ZIP_STORED
                    with open(patched_c2, "rb") as f:
                        zout.writestr(zi, f.read())
                elif info.filename == "classes3.dex":
                    zi = zipfile.ZipInfo("classes3.dex", date_time=(2008, 1, 1, 0, 0, 0))
                    zi.compress_type = zipfile.ZIP_STORED
                    with open(patched_c3, "rb") as f:
                        zout.writestr(zi, f.read())
                else:
                    zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                    zi.compress_type = info.compress_type
                    zout.writestr(zi, zin.read(info.filename))

        subprocess.run([ZIPALIGN, "-f", "-p", "4", unaligned_jar, OUT_JAR], check=True)
        subprocess.run([ZIPALIGN, "-c", "-p", "4", OUT_JAR], check=True)
        print("Built aligned patched services.jar ->", OUT_JAR)


if __name__ == "__main__":
    main()
