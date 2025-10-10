def set_labels_atomic(label_to_color: Dict[str, RGBColor]) -> bool:
    """
    ?щ윭 ?쇰꺼????踰덉뿉 ?곸슜(諛곗튂)?섏뿬 以묎컙 ?꾨젅??????on/紐⑤몢 off)??諛⑹?.
    stage ?쒖떆泥섎읆 ?곹샇諛고???媛깆떊???곹빀. 吏??sleep) ?놁쓬.
    """
    if kb is None or km is None:
        raise RuntimeError("癒쇱? connect()瑜??몄텧?댁빞 ?⑸땲??")

    # ?꾩옱 ??諛곗뿴??湲곕컲?쇰줈 ??뼱?곌린 ?? ??踰덉뿉 set_colors ?곸슜
    try:
        # km媛 媛由ы궎???ㅼ젣 ?ㅻ낫???붾컮?댁뒪瑜??곗꽑 ?ъ슜(?μ튂 遺덉씪移?諛⑹?)
        dev = None
        try:
            dev = km._load_keyboard()  # type: ignore[attr-defined]
        except Exception:
            dev = None
        device = dev or kb

        if device is None:
            return False

        # ??긽 direct 紐⑤뱶 蹂댁옣
        try:
            device.set_mode("direct")
        except Exception:
            pass

        try:
            _refresh_device_leds(device)
        except Exception:
            pass

        # colors ?먮낯 ?뺣낫
        colors: List[RGBColor] = [led.color for led in device.leds]

        # ?곸꽭 ?붾쾭洹?異쒕젰 ?좉? (?섍꼍蹂??RGB_ATOMIC_DEBUG=1|true|yes|y)
        dbg = False
        try:
            import os
            dbg = str(os.environ.get("RGB_ATOMIC_DEBUG", "")).strip().lower() in ("1", "true", "y", "yes")
        except Exception:
            dbg = False
        # Runtime override (no env needed)
        try:
            if _ATOMIC_DEBUG:
                dbg = True
        except Exception:
            pass

        changes: List[Tuple[int, RGBColor]] = []
        for lab, col in label_to_color.items():
            key = lab.lower()
            idx = km.label_to_index.get(key)
            if idx is None or not (0 <= idx < len(colors)):
                if dbg:
                    try:
                        print(f"[RGB-ATOMIC] resolve-miss label='{lab}' -> idx=None (leds={len(colors)})")
                    except Exception:
                        pass
                continue
            # Skip no-ops based on last-state cache
            try:
                tgt = (int(col.red), int(col.green), int(col.blue))
                if _LAST_LABEL_COLOR.get(key) == tgt:
                    if dbg:
                        try:
                            print(f"[RGB-ATOMIC] skip-noop idx={idx} label='{lab}'")
                        except Exception:
                            pass
                    continue
            except Exception:
                pass
            colors[idx] = col
            changes.append((idx, col))
            if dbg:
                try:
                    print(f"[RGB-ATOMIC] plan idx={idx} label='{lab}' color=({col.red},{col.green},{col.blue})")
                except Exception:
                    pass

        if not changes:
            # Nothing to update (all were no-ops or unresolved); treat as success
            if dbg:
                try:
                    print("[RGB-ATOMIC] no-op (no changes)")
                except Exception:
                    pass
            return True

        ok = False
        try:
            device.set_colors(colors)
            ok = True
        except Exception as ex:
            ok = False
            if dbg:
                try:
                    print(f"[RGB-ATOMIC] device.set_colors failed: {ex}")
                except Exception:
                    pass

        # ?덉쟾 ?뺣낫: 蹂寃쎈맂 ?ㅻ뒗 媛쒕퀎濡쒕룄 ??踰????곸슜
        ok_any = False
        if not ok:
            for idx, col in changes:
                try:
                    device.leds[idx].set_color(col)
                    ok_any = True
                except Exception as ex:
                    if dbg:
                        try:
                            print(f"[RGB-ATOMIC] per-key set fail idx={idx}: {ex}")
                        except Exception:
                            pass

        if ok or ok_any:
            try:
                time.sleep(max(0.0, float(_APPLY_DELAY_MS) / 1000.0))
            except Exception:
                pass
            if dbg:
                try:
                    mode = "batch" if ok else "per-key"
                    print(f"[RGB-ATOMIC] applied via {mode}; changes={len(changes)}")
                except Exception:
                    pass
            # Update last-state cache on success
            try:
                for lab, col in label_to_color.items():
                    _LAST_LABEL_COLOR[lab.lower()] = (int(col.red), int(col.green), int(col.blue))
            except Exception:
                pass
            return True
        # Final fallback: use label-driven km.set for each entry
        applied = False
        for lab, col in label_to_color.items():
            try:
                if km.set(lab, col):
                    applied = True
                    if dbg:
                        try:
                            print(f"[RGB-ATOMIC] fallback km.set ok label='{lab}'")
                        except Exception:
                            pass
            except Exception as ex2:
                if dbg:
                    try:
                        print(f"[RGB-ATOMIC] fallback km.set fail label='{lab}': {ex2}")
                    except Exception:
                        pass
        if applied:
            try:
                time.sleep(max(0.0, float(_APPLY_DELAY_MS) / 1000.0))
            except Exception:
                pass
            # Update cache best-effort
            try:
                for lab, col in label_to_color.items():
                    _LAST_LABEL_COLOR[lab.lower()] = (int(col.red), int(col.green), int(col.blue))
            except Exception:
                pass
            return True
        if dbg:
            try:
                print("[RGB-ATOMIC] apply failed; no changes took effect")
            except Exception:
                pass
        return False
    except Exception as ex:
        try:
            import os
            if str(os.environ.get("RGB_ATOMIC_DEBUG", "")).strip().lower() in ("1", "true", "y", "yes"):
                print(f"[RGB-ATOMIC] exception: {ex}")
        except Exception:
            pass
        return False
