/**
 * Codex Pet atlas player — catalog from Runtime pets.list (download + Cache API),
 * with bundled ./sprites/catalog.json as offline fallback.
 * Atlas: 8×9 × 192×208; only cycle non-empty frames.
 */
(function (global) {
  const CELL_W = 192;
  const CELL_H = 208;
  const FALLBACK_CATALOG = "./sprites/catalog.json";
  const CACHE_NAME = "agentdock-pets-v1";

  const ROW = {
    idle: 0,
    waving: 3,
    failed: 5,
    waiting: 6,
    review: 8,
  };

  const FRAMES = {
    0: 6,
    1: 8,
    2: 8,
    3: 4,
    4: 5,
    5: 8,
    6: 6,
    7: 6,
    8: 6,
  };

  /** @type {Record<string, {id:string,label:string,src:string,url?:string,sheet?:string}>} */
  let PETS = {};
  let DEFAULT_PET = "monthly-salary-cat";
  let catalogReady = null;
  let remoteBase = "";
  let assetsPort = 8766;

  function moodRow(mood) {
    if (mood === "listen") return ROW.waiting;
    if (mood === "busy") return ROW.review;
    if (mood === "speak") return ROW.waving;
    if (mood === "err" || mood === "offline") return ROW.failed;
    return ROW.idle;
  }

  function joinUrl(base, sheet) {
    const b = String(base || "").replace(/\/+$/, "");
    const s = String(sheet || "").replace(/^\/+/, "");
    return b + "/" + s;
  }

  /** Prefer same host as WS URL so phones hit LAN IP, not 127.0.0.1. */
  function baseFromWs(wsUrl, port, serverBase) {
    try {
      const u = new URL(String(wsUrl).replace(/^ws/i, "http"));
      u.port = String(port || assetsPort || 8766);
      u.pathname = "/pets";
      u.search = "";
      u.hash = "";
      return u.origin + "/pets";
    } catch (_) {
      return serverBase || remoteBase || "";
    }
  }

  async function cachedObjectUrl(url) {
    if (!url) return url;
    try {
      if (!("caches" in global)) return url;
      const cache = await caches.open(CACHE_NAME);
      let res = await cache.match(url);
      if (!res) {
        res = await fetch(url);
        if (res.ok) await cache.put(url, res.clone());
      }
      if (!res || !res.ok) return url;
      const blob = await res.blob();
      return URL.createObjectURL(blob);
    } catch (err) {
      console.warn("pet cache miss, direct fetch", url, err);
      return url;
    }
  }

  function applyPetsList(list, defaultId, baseUrl) {
    const map = {};
    const pets = Array.isArray(list) ? list : [];
    for (const p of pets) {
      if (!p || !p.id) continue;
      const sheet = p.sheet || p.id + "/spritesheet.webp";
      const src = p.src || (baseUrl ? joinUrl(baseUrl, sheet) : "./sprites/" + String(sheet).replace(/^\/+/, ""));
      map[p.id] = {
        id: p.id,
        label: p.label || p.id,
        sheet,
        src,
        url: p.url || "",
      };
    }
    if (!Object.keys(map).length) return false;
    PETS = map;
    DEFAULT_PET =
      defaultId && map[defaultId] ? defaultId : Object.keys(map)[0];
    catalogReady = Promise.resolve({ pets: PETS, defaultId: DEFAULT_PET });
    return true;
  }

  /**
   * Apply Runtime pets.list.result. Client derives base from WS when possible.
   * @returns {{pets: object, defaultId: string}|null}
   */
  function applyRemoteCatalog(payload, wsUrl) {
    const p = payload || {};
    if (p.assets_port != null) assetsPort = Number(p.assets_port) || assetsPort;
    const serverBase = p.base_url || "";
    remoteBase = baseFromWs(wsUrl, assetsPort, serverBase) || serverBase;
    if (!applyPetsList(p.pets, p.default, remoteBase)) return null;
    return { pets: PETS, defaultId: DEFAULT_PET };
  }

  function loadCatalog() {
    if (catalogReady) return catalogReady;
    catalogReady = fetch(FALLBACK_CATALOG)
      .then((r) => {
        if (!r.ok) throw new Error("catalog " + r.status);
        return r.json();
      })
      .then((data) => {
        if (!applyPetsList(data.pets, data.default, null)) {
          throw new Error("empty pet catalog");
        }
        // rewrite to bundled paths
        for (const id of Object.keys(PETS)) {
          const sheet = PETS[id].sheet || id + "/spritesheet.webp";
          PETS[id].src = "./sprites/" + String(sheet).replace(/^\/+/, "");
        }
        return { pets: PETS, defaultId: DEFAULT_PET };
      })
      .catch((err) => {
        console.warn("pet catalog load failed, using fallback", err);
        PETS = {
          "monthly-salary-cat": {
            id: "monthly-salary-cat",
            label: "Monthly salary cat",
            src: "./sprites/monthly-salary-cat/spritesheet.webp",
            url: "",
          },
        };
        DEFAULT_PET = "monthly-salary-cat";
        return { pets: PETS, defaultId: DEFAULT_PET };
      });
    return catalogReady;
  }

  function createPixelBot(canvas, initialPetId) {
    canvas.width = CELL_W;
    canvas.height = CELL_H;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;

    let mood = "offline";
    let tick = 0;
    let timer = null;
    let sheet = null;
    let ready = false;
    let lastKey = "";
    let petId = initialPetId || DEFAULT_PET;
    let loadGen = 0;
    let objectUrl = null;

    function resolvePet(id) {
      return PETS[id] || PETS[DEFAULT_PET] || Object.values(PETS)[0];
    }

    function loadSheet(id) {
      const pet = resolvePet(id);
      if (!pet) return;
      petId = pet.id;
      ready = false;
      sheet = null;
      lastKey = "";
      const gen = ++loadGen;
      if (objectUrl) {
        try {
          URL.revokeObjectURL(objectUrl);
        } catch (_) {}
        objectUrl = null;
      }
      cachedObjectUrl(pet.src).then((src) => {
        if (gen !== loadGen) return;
        if (src && src.startsWith("blob:")) objectUrl = src;
        const img = new Image();
        img.onload = () => {
          if (gen !== loadGen) return;
          sheet = img;
          ready = true;
          redraw(true);
        };
        img.onerror = () => {
          if (gen !== loadGen) return;
          console.warn("Missing spritesheet at", pet.src);
        };
        img.src = src;
      });
    }

    function redraw(force) {
      if (!ready || !sheet) return;
      const row = moodRow(mood);
      const n = FRAMES[row] || 1;
      const col = tick % n;
      const key = petId + ":" + row + ":" + col;
      if (!force && key === lastKey) return;
      lastKey = key;

      ctx.clearRect(0, 0, CELL_W, CELL_H);
      ctx.drawImage(
        sheet,
        col * CELL_W,
        row * CELL_H,
        CELL_W,
        CELL_H,
        0,
        0,
        CELL_W,
        CELL_H
      );
    }

    const booted = loadCatalog().then(() => {
      if (!PETS[petId]) petId = DEFAULT_PET;
      loadSheet(petId);
    });

    return {
      ready: booted,
      setMood(next) {
        mood = next || "idle";
        tick = 0;
        lastKey = "";
        redraw(true);
      },
      setPet(id) {
        if (!PETS[id] || id === petId) return;
        loadSheet(id);
        tick = 0;
      },
      /** Reload current pet after remote catalog applied. */
      reload() {
        loadSheet(petId);
      },
      getPet() {
        return petId;
      },
      listPets() {
        return Object.keys(PETS).map((id) => ({
          id,
          label: PETS[id].label,
          url: PETS[id].url,
        }));
      },
      start() {
        if (timer) return;
        timer = setInterval(() => {
          tick += 1;
          redraw(false);
        }, 160);
        redraw(true);
      },
      stop() {
        if (timer) clearInterval(timer);
        timer = null;
      },
    };
  }

  function fillPetSelect(selectEl, selectedId) {
    return loadCatalog().then(({ pets, defaultId }) => {
      const cur = selectedId && pets[selectedId] ? selectedId : defaultId;
      if (selectEl) {
        selectEl.innerHTML = "";
        for (const id of Object.keys(pets)) {
          const opt = document.createElement("option");
          opt.value = id;
          opt.textContent = pets[id].label;
          if (id === cur) opt.selected = true;
          selectEl.appendChild(opt);
        }
      }
      return cur;
    });
  }

  function refreshPetSelect(selectEl, selectedId) {
    const pets = PETS;
    const defaultId = DEFAULT_PET;
    const cur = selectedId && pets[selectedId] ? selectedId : defaultId;
    selectEl.innerHTML = "";
    for (const id of Object.keys(pets)) {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = pets[id].label;
      if (id === cur) opt.selected = true;
      selectEl.appendChild(opt);
    }
    return cur;
  }

  global.PixelBot = {
    createPixelBot,
    loadCatalog,
    fillPetSelect,
    refreshPetSelect,
    applyRemoteCatalog,
    get PETS() {
      return PETS;
    },
    get DEFAULT_PET() {
      return DEFAULT_PET;
    },
  };
})(window);
