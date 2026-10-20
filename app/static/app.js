"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const zustand = { datei: null, sprachen: [], einstellungen: {}, status: {}, logAb: {} };

async function api(pfad, opt = {}) {
  const r = await fetch(pfad, opt);
  let daten = null;
  try { daten = await r.json(); } catch { /* keine JSON-Antwort */ }
  if (!r.ok) throw new Error((daten && daten.detail) || ("Fehler " + r.status));
  return daten;
}
const post = (pfad, daten) => api(pfad, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(daten) });
const groesse = b => b > 1e9 ? (b / 1e9).toFixed(1).replace(".", ",") + " GB" : Math.round(b / 1e6) + " MB";
const dauer = s => s < 60 ? s + " s" : s < 3600 ? Math.floor(s / 60) + " min " + (s % 60) + " s" : Math.floor(s / 3600) + " h " + Math.floor(s % 3600 / 60) + " min";

/* ------------------------------------------------ 1  Kurs */
const ablage = $("#ablage"), dateiFeld = $("#datei");
function dateiSetzen(f) {
  if (!f) return;
  if (!f.name.toLowerCase().endsWith(".mbz")) { alert("Das ist keine Moodle-Sicherung. Bitte eine .mbz-Datei wählen."); return; }
  zustand.datei = f;
  ablage.classList.add("gewaehlt");
  $("#ablage_titel").textContent = f.name;
  $("#ablage_info").textContent = groesse(f.size) + " · zum Ändern einfach eine andere Datei hineinziehen";
  pruefen();
}
dateiFeld.addEventListener("change", () => dateiSetzen(dateiFeld.files[0]));
ablage.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); dateiFeld.click(); } });
["dragenter", "dragover"].forEach(t => document.addEventListener(t, e => { e.preventDefault(); ablage.classList.add("ziehen"); }));
["dragleave", "drop"].forEach(t => document.addEventListener(t, e => { e.preventDefault(); if (t === "drop" || !e.relatedTarget) ablage.classList.remove("ziehen"); }));
document.addEventListener("drop", e => dateiSetzen(e.dataTransfer.files[0]));

/* ------------------------------------------------ 2  Sprache */
async function sprachenLaden() {
  zustand.sprachen = await api("/api/sprachen");
  const zuletzt = (zustand.einstellungen.zuletzt_sprachen || []).map(c => zustand.sprachen.find(s => s.code === c)).filter(Boolean);
  const option = s => `<option value="${s.code}">${s.name}${s.eigen && s.eigen !== s.name ? " – " + s.eigen : ""}</option>`;
  $("#sprache").insertAdjacentHTML("beforeend",
    (zuletzt.length ? `<optgroup label="Zuletzt verwendet">${zuletzt.map(option).join("")}</optgroup>` : "")
    + `<optgroup label="Alle Sprachen A–Z">${zustand.sprachen.map(option).join("")}</optgroup>`);
  $("#sprache").addEventListener("change", () => { ordnerVorschlag(); spracheInfo(); pruefen(); });
}
const spracheWahl = () => $("#sprache").value;
function spracheInfo() {
  const s = zustand.sprachen.find(x => x.code === spracheWahl()), info = $("#spracheinfo");
  if (!s) return;
  info.className = "erklaerung " + (s.stimme ? "gut" : "warn");
  info.textContent = s.stimme
    ? `✓ Kürzel ${s.code.toUpperCase()} · Microsoft-Stimme vorhanden – fehlende Videos können kostenlos vertont werden.`
    : `Kürzel ${s.code.toUpperCase()} · Für diese Sprache hat Microsoft keine Stimme: Texte werden übersetzt, Videos nur mit HeyGen oder aus dem Videoordner.`;
}
const gewaehlt = n => ($(`input[name=${n}]:checked`) || {}).value;

/* ------------------------------------------------ 3  Videos */
const ordnerFeld = $("#videoordner");
let ordnerTimer;
ordnerFeld.addEventListener("input", () => { clearTimeout(ordnerTimer); ordnerTimer = setTimeout(ordnerZaehlen, 400); pruefen(); });

// Ordnerregel <Bereich>/<SPR>/Videos: beim Sprachwechsel den Nachbarordner vorschlagen
function ordnerVorschlag() {
  const code = spracheWahl(); if (!code) return;
  const v = ordnerFeld.value.trim();
  const m = v.match(/^(.*[\\/])([A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?)([\\/]Videos[\\/]?)$/i);
  if (m && m[2].toLowerCase() !== code) { ordnerFeld.value = m[1] + code.toUpperCase() + m[3].replace(/[\\/]$/, ""); ordnerZaehlen(); }
}

async function ordnerZaehlen() {
  const info = $("#ordnerinfo"), p = ordnerFeld.value.trim().replace(/^"|"$/g, "");
  if (!p) { info.className = "erklaerung"; info.innerHTML = info.dataset.standard; return; }
  try {
    const d = await api("/api/ordner?pfad=" + encodeURIComponent(p));
    info.className = "erklaerung gut";
    info.textContent = d.videos ? `✓ ${d.videos} Video(s) in diesem Ordner – passende werden übernommen, der Rest wird erstellt.`
      : "✓ Ordner gefunden, noch leer – alle Videos werden neu erstellt und hier abgelegt.";
  } catch (e) {
    info.className = "erklaerung warn";
    info.textContent = /gibt es nicht/.test(e.message) ? "Diesen Ordner gibt es noch nicht – er wird angelegt, wenn der übergeordnete Ordner existiert." : e.message;
  }
}

// Ordnerauswahl
const dlg = $("#ordnerdialog");
let dlgPfad = "", dlgEltern = null;
async function ordnerZeigen(p) {
  try {
    const d = await api("/api/ordner?pfad=" + encodeURIComponent(p));
    dlgPfad = d.pfad; dlgEltern = d.eltern;
    $("#ordnerpfad").textContent = d.pfad || "Start";
    $("#hoch").disabled = !d.pfad;
    $("#ordner_ok").disabled = !d.pfad;
    $("#ordnervideos").textContent = d.pfad ? (d.videos ? d.videos + " Video(s) hier" : "keine Videos hier") : "";
    $("#ordnerliste").innerHTML = d.ordner.length ? "" : '<li class="leerzeile">keine Unterordner</li>';
    d.ordner.forEach(o => {
      const li = document.createElement("li"), b = document.createElement("button");
      b.type = "button"; b.textContent = o.name; b.onclick = () => ordnerZeigen(o.pfad);
      li.append(b); $("#ordnerliste").append(li);
    });
  } catch (e) { alert(e.message); }
}
$("#durchsuchen").onclick = () => { ordnerZeigen(ordnerFeld.value.trim() || zustand.einstellungen.letzter_videoordner || ""); dlg.showModal(); };
$("#hoch").onclick = () => ordnerZeigen(dlgEltern || "");
dlg.addEventListener("close", () => { if (dlg.returnValue === "ok" && dlgPfad) { ordnerFeld.value = dlgPfad; ordnerZaehlen(); pruefen(); } });

$$("input[name=modus]").forEach(i => i.addEventListener("change", () => {
  $("#stimmwahl").hidden = gewaehlt("modus") !== "edge"; pruefen();
}));

/* ------------------------------------------------ Zusammenfassung & Start */
function pruefen() {
  const code = spracheWahl(), s = zustand.sprachen.find(x => x.code === code), modus = gewaehlt("modus");
  $('[data-nr="1"]').classList.toggle("erledigt", !!zustand.datei);
  $('[data-nr="2"]').classList.toggle("erledigt", !!code);
  $('[data-nr="3"]').classList.toggle("erledigt", !!ordnerFeld.value.trim());
  const fehlt = [];
  if (!zustand.datei) fehlt.push("einen Kurs");
  if (!code) fehlt.push("eine Sprache");
  if (!ordnerFeld.value.trim()) fehlt.push("den Videoordner");
  const z = $("#zusammenfassung");
  if (fehlt.length) z.textContent = "Noch wählen: " + fehlt.join(", ") + ".";
  else z.innerHTML = `<b>${zustand.datei.name}</b> → <b>${s.name}</b>, fehlende Videos mit <b>${modus === "heygen" ? "HeyGen" : "Microsoft-Stimme"}</b>`;
  $("#start").disabled = fehlt.length > 0;
}

$("#formular").addEventListener("submit", e => {
  e.preventDefault();
  if (zustand.einstellungen.ki.fehlt) { alert(zustand.einstellungen.ki.fehlt); einstellungenZeigen(); return; }
  if (gewaehlt("modus") === "heygen" && !zustand.einstellungen.heygen) { alert("Für HeyGen fehlt noch der API-Schlüssel. Bitte im Zahnrad oben rechts eintragen."); einstellungenZeigen(); return; }
  const fd = new FormData();
  fd.append("mbz", zustand.datei);
  fd.append("sprache", spracheWahl());
  fd.append("videoordner", ordnerFeld.value.trim());
  fd.append("modus", gewaehlt("modus"));
  fd.append("stimme", gewaehlt("stimme"));
  fd.append("kursname", $("#kursname").value);
  fd.append("quizid", $("#quizid").value);
  fd.append("klein", $("#klein").checked);
  fd.append("moodleprobe", $("#moodleprobe").checked);
  const leiste = $("#hochladen"), knopf = $("#start");
  leiste.hidden = false; knopf.disabled = true;
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/auftrag");
  xhr.upload.onprogress = ev => {
    const p = ev.lengthComputable ? ev.loaded / ev.total : 0;
    $("i", leiste).style.width = (p * 100) + "%";
    $("span", leiste).textContent = p < 1 ? `Kurs wird übergeben … ${Math.round(p * 100)} %` : "wird angelegt …";
  };
  xhr.onload = () => {
    leiste.hidden = true; pruefen();
    let d = {}; try { d = JSON.parse(xhr.responseText); } catch { }
    if (xhr.status >= 400) { alert(d.detail || "Fehler beim Anlegen"); return; }
    holeAuftraege();
  };
  xhr.onerror = () => { leiste.hidden = true; pruefen(); alert("Verbindung zur App unterbrochen."); };
  xhr.send(fd);
});

/* ------------------------------------------------ Aufträge */
const ZUSTAND = { wartet: ["in der Warteschlange", ""], laeuft: ["läuft", "gelb"], fertig: ["fertig", "gruen"], fehler: ["Fehler", "rot"], abgebrochen: ["abgebrochen", "rot"] };

function auftragZeichnen(d) {
  let el = document.getElementById("a_" + d.id);
  if (!el) {
    el = $("#auftragsvorlage").content.firstElementChild.cloneNode(true);
    el.id = "a_" + d.id;
    $(".a_abbrechen", el).onclick = async () => { if (confirm("Diesen Auftrag abbrechen? Erledigtes bleibt erhalten.")) await post(`/api/auftrag/${d.id}/abbrechen`, {}); };
    const leer = $("#liste .leer"); if (leer) leer.remove();
    $("#liste").prepend(el);
  }
  const s = zustand.sprachen.find(x => x.code === d.sprache) || { name: d.sprache };
  $(".a_titel", el).textContent = `${s.name} (${(d.sprache||"").toUpperCase()})`;
  $(".a_unter", el).textContent = `${d.kurs} · ${d.modus === "heygen" ? "HeyGen" : "Microsoft-Stimme"} · ${dauer(d.dauer_s)}`;
  const [txt, farbe] = ZUSTAND[d.zustand] || [d.zustand, ""];
  const sch = $(".a_zustand", el); sch.textContent = txt; sch.className = "a_zustand schild " + farbe;
  el.className = "auftrag " + d.zustand + (["wartet", "laeuft"].includes(d.zustand) ? " aktiv" : "");
  const erledigt = d.schritte.filter(x => ["fertig", "warnung", "uebersprungen"].includes(x.zustand)).length;
  const laeuft = d.schritte.some(x => x.zustand === "laeuft") ? 0.5 : 0;
  $(".fortschritt i", el).style.width = (d.zustand === "fertig" ? 100 : (erledigt + laeuft) / d.schritte.length * 100) + "%";
  $(".schritte", el).innerHTML = d.schritte.map(x => `<li class="${x.zustand}"><span class="punkt"></span><span>${x.name}</span><span class="info">${x.info || ""}</span></li>`).join("");
  let fehler = $(".fehlertext", el);
  if (d.fehler) { if (!fehler) { fehler = document.createElement("p"); fehler.className = "fehlertext"; $(".schritte", el).after(fehler); } fehler.textContent = d.fehler; }
  $(".a_hinweise", el).innerHTML = d.hinweise.length ? "<b>Bitte beachten</b><ul>" + [...new Set(d.hinweise)].slice(0, 6).map(h => `<li>${h.replace(/</g, "&lt;")}</li>`).join("") + "</ul>" : "";
  $(".a_ergebnisse", el).innerHTML = d.ergebnisse.map((e, i) => `
    <div class="ergebnis"><div class="wer"><b>${e.empfohlen ? "⭐ " : ""}${e.name}</b><small>${e.mb} MB${e.empfohlen ? " · diese Datei in Moodle hochladen" : ""} · ${e.anzeige}</small></div>
      <a class="knopf haupt klein" href="/api/auftrag/${d.id}/datei/${i}">Herunterladen</a>
      ${zustand.status.container ? "" : `<button class="knopf zweit klein" data-zeigen="${i}">Im Ordner zeigen</button>`}
    </div>`).join("");
  $$("[data-zeigen]", el).forEach(b => b.onclick = () => post(`/api/auftrag/${d.id}/zeigen/${b.dataset.zeigen}`, {}));
  if (d.log.length) {
    const pre = $(".a_protokoll pre", el), unten = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8;
    pre.textContent += d.log.join("\n") + "\n";
    if (unten) pre.scrollTop = pre.scrollHeight;
  }
  zustand.logAb[d.id] = d.log_bis;
}

async function holeAuftraege() {
  try {
    const liste = await api("/api/auftraege");
    for (const a of liste.reverse()) {
      const d = await api(`/api/auftrag/${a.id}?ab=${zustand.logAb[a.id] || 0}`);
      auftragZeichnen(d);
    }
  } catch { /* App kurz nicht erreichbar */ }
}
setInterval(holeAuftraege, 2000);

/* ------------------------------------------------ Einstellungen */
const edlg = $("#einstellungsdialog");
const ANBIETER_TEXT = {
  anthropic: { kurz: "Claude", info: "Claude direkt bei Anthropic. Vorschlag: claude-haiku-5-5 – schnell und günstig (wenige Cent je Kurs).", platz: "sk-ant-…" },
  openrouter: { kurz: "OpenRouter", info: "Ein Schlüssel für Hunderte Modelle (Claude, GPT, Gemini, Mistral, Llama …). Einige sind kostenlos. Schlüssel gibt es auf openrouter.ai.", platz: "sk-or-…" },
  openai: { kurz: "Eigener Dienst", info: "Jeder Dienst mit OpenAI-Schnittstelle: OpenAI selbst, Ollama oder LM Studio auf dem eigenen Rechner, ein Schul-Server.", platz: "nur wenn der Dienst einen verlangt" },
};
let gewaehlterAnbieter = null;

async function einstellungenLaden() {
  zustand.einstellungen = await api("/api/einstellungen");
  $("#s_heygen").placeholder = zustand.einstellungen.heygen || "optional";
}

function anbieterZeigen(id) {
  gewaehlterAnbieter = id;
  const ki = zustand.einstellungen.ki, a = ki.anbieter_liste.find(x => x.id === id), t = ANBIETER_TEXT[id];
  $$("#anbieter input").forEach(i => i.checked = i.value === id);
  $("#anbieterinfo").textContent = t.info;
  $("#urlzeile").hidden = id !== "openai";
  $("#s_url").value = ki.url || "";
  $("#s_modell").value = a.modell || a.standard_modell;
  $("#s_modell").placeholder = a.standard_modell || "Modellname, z. B. llama3.1";
  $("#s_ki").value = "";
  $("#s_ki").placeholder = a.schluessel || t.platz;
  $("#schluesselinfo").textContent = a.schluessel ? "– hinterlegt, leer lassen = behalten" : (a.schluessel_noetig ? "– nötig" : "– meist nicht nötig");
  $("#t_ki").textContent = ""; $("#t_ki").className = "testergebnis";
  modelleLaden(id);
}

async function modelleLaden(id) {
  $("#modellvorschlaege").innerHTML = ""; $("#modellzahl").textContent = "";
  // Vorschlagsliste gehoert zum gerade gespeicherten Anbieter; nur laden, wenn er passt
  if (zustand.einstellungen.ki.anbieter !== id) { $("#modellzahl").textContent = "– Liste erscheint nach dem Speichern"; return; }
  const r = await api("/api/modelle").catch(() => ({ modelle: [] }));
  if (gewaehlterAnbieter !== id) return;
  $("#modellvorschlaege").innerHTML = r.modelle.map(m => `<option value="${m.id}">${m.name}${m.info ? " · " + m.info : ""}</option>`).join("");
  $("#modellzahl").textContent = r.modelle.length ? `– ${r.modelle.length} zur Auswahl, einfach lostippen` : "";
}

async function kiSpeichern() {
  const daten = { ki_anbieter: gewaehlterAnbieter, ki_modell: $("#s_modell").value.trim() };
  if (gewaehlterAnbieter === "openai") daten.openai_url = $("#s_url").value.trim();
  if ($("#s_ki").value) daten.schluessel = { [gewaehlterAnbieter]: $("#s_ki").value };
  zustand.einstellungen = await post("/api/einstellungen", daten);
}

function einstellungenZeigen() {
  const ki = zustand.einstellungen.ki;
  $("#anbieter").innerHTML = ki.anbieter_liste.map(a =>
    `<label><input type="radio" name="anbieter" value="${a.id}"><span>${ANBIETER_TEXT[a.id].kurz}</span></label>`).join("");
  $$("#anbieter input").forEach(i => i.onchange = () => anbieterZeigen(i.value));
  anbieterZeigen(ki.anbieter);
  $("#s_heygen").value = "";
  $$(".testergebnis").forEach(p => { p.textContent = ""; p.className = "testergebnis"; });
  const st = zustand.status, punkt = (ok, t) => `<span class="schild ${ok ? "gruen" : "rot"}">${ok ? "✓" : "✗"} ${t}</span>`;
  laborAnzeigen();
  vorlesenZeigen();
  $("#systemstand").innerHTML = punkt(st.skill, "Übersetzungs-Skill") + punkt(st.ffmpeg, "ffmpeg") + punkt(st.edge_tts, "Microsoft-Stimmen")
    + punkt(st.whisper, "Spracherkennung") + punkt(st.verkleinern, "Verkleinern");
  edlg.showModal();
}
$("#zahnrad").onclick = einstellungenZeigen;
$("#ki_hinweis").onclick = einstellungenZeigen;
$("#speichern").onclick = async e => {
  e.preventDefault();
  await kiSpeichern();
  if ($("#s_heygen").value) await post("/api/einstellungen", { heygen: $("#s_heygen").value });
  await vorlesenSpeichern();
  await einstellungenLaden(); edlg.close(); warnungZeigen();
};
$$("[data-test]").forEach(b => b.onclick = async () => {
  const welcher = b.dataset.test, aus = $("#t_" + welcher);
  if (welcher === "stimme") await vorlesenSpeichern();
  if (welcher === "ki") { const vorher = zustand.einstellungen.ki.anbieter; await kiSpeichern(); if (vorher !== gewaehlterAnbieter) modelleLaden(gewaehlterAnbieter); }
  else if ($("#s_heygen").value) zustand.einstellungen = await post("/api/einstellungen", { heygen: $("#s_heygen").value });
  aus.textContent = welcher === "ki" ? "übersetze einen Probesatz …" : "prüfe …"; aus.className = "testergebnis";
  const r = await post("/api/einstellungen/testen", { welcher });
  aus.textContent = r.text; aus.className = "testergebnis " + (r.ok ? "ok" : "nein");
  einstellungenLaden();
});

function warnungZeigen() {
  const warn = $("#warnleiste"), ki = zustand.einstellungen.ki;
  if (!zustand.einstellungen.datenschutz_gelesen) {
    warn.hidden = false;
    warn.innerHTML = 'Bitte vor dem ersten Einsatz lesen: <a href="datenschutz.html">Welche Daten gehen an welchen Dienst?</a> '
      + '(mit Vorlage für die Schulleitung) <button class="knopf zweit klein" id="ds_ok">Gelesen</button>';
    $("#ds_ok").onclick = async () => { zustand.einstellungen = await post("/api/einstellungen", { datenschutz_gelesen: true }); warnungZeigen(); };
  }
  else if (ki.fehlt) { warn.hidden = false; warn.textContent = "Einmalig nötig: " + ki.fehlt; }
  else warn.hidden = true;
  const a = ki.anbieter_liste.find(x => x.id === ki.anbieter);
  $("#ki_hinweis").textContent = `Übersetzt wird mit ${a.name} · ${ki.modell}`;
}

/* ------------------------------------------------ Vorlesestimme */
function vorlesenZeigen(art) {
  const v = zustand.einstellungen.vorlesen;
  art = art || v.art;
  $$("input[name=vorlesen]").forEach(i => { i.checked = i.value === art; i.onchange = () => vorlesenZeigen(i.value); });
  $("#azurezeilen").hidden = art !== "azure";
  $("#s_azure").value = ""; $("#s_azure").placeholder = v.schluessel || "Schlüssel aus dem Azure-Portal (Speech-Dienst)";
  $("#s_region").value = v.region || "germanywestcentral";
  $("#vorleseinfo").textContent = art === "azure"
    ? "Offizieller Weg von Microsoft mit eigenem Konto der Schule: dieselben Stimmen, Server in der EU wählbar, ein kostenloses Monatskontingent."
    : "Kostenlos und ohne Konto, aber von Microsoft nicht offiziell für andere Programme freigegeben – kann jederzeit gesperrt werden. Für die Weitergabe durch Schule oder Land: Azure Speech.";
}
async function vorlesenSpeichern() {
  const art = ($("input[name=vorlesen]:checked") || {}).value;
  if (!art) return;
  const daten = { vorlesen_art: art, azure_region: $("#s_region").value.trim() };
  if ($("#s_azure").value) daten.schluessel = { azure: $("#s_azure").value };
  zustand.einstellungen = await post("/api/einstellungen", daten);
}

/* ------------------------------------------------ Moodle-Prüfung */
let laborTimer = null;
async function laborAnzeigen() {
  clearTimeout(laborTimer);
  const l = await api("/api/moodlelabor").catch(() => null), stand = $("#laborstand"), knopf = $("#labor_einrichten");
  if (!l) return;
  const log = $("#laborlog");
  knopf.hidden = !l.eingebaut || l.bereit || l.laeuft;
  if (!l.eingebaut) { stand.className = "erklaerung warn"; stand.textContent = "In dieser Fassung nicht enthalten."; }
  else if (l.laeuft) { stand.className = "erklaerung"; stand.textContent = "Wird eingerichtet … (Fenster darf offen bleiben, Sie können weiterarbeiten)"; }
  else if (l.bereit) { stand.className = "erklaerung gut"; stand.textContent = "✓ Eingerichtet – jede fertige Sicherung wird probeweise eingespielt."; }
  else { stand.className = "erklaerung"; stand.textContent = l.ergebnis && l.ergebnis !== "fertig" ? l.ergebnis : "Noch nicht eingerichtet."; }
  log.hidden = !(l.laeuft || (l.ergebnis && l.ergebnis !== "fertig"));
  log.textContent = l.log.join("\n");
  if (l.laeuft && edlg.open) laborTimer = setTimeout(laborAnzeigen, 3000);
}
$("#labor_einrichten").onclick = async () => {
  if (!confirm("Die Moodle-Prüfung lädt einmalig rund 450 MB aus den offiziellen Quellen (PHP, MariaDB, Moodle 4.5, H5P-Plugin) und richtet sie auf diesem Rechner ein. Das dauert 10–20 Minuten. Jetzt starten?")) return;
  await post("/api/moodlelabor/einrichten", {});
  laborAnzeigen();
};

/* ------------------------------------------------ Start */
(async function start() {
  $("#ordnerinfo").dataset.standard = $("#ordnerinfo").innerHTML;
  zustand.status = await api("/api/status");
  await einstellungenLaden();
  await sprachenLaden();
  const e = zustand.einstellungen;
  if (e.letzter_videoordner) { ordnerFeld.value = e.letzter_videoordner; ordnerZaehlen(); }
  if (e.letzte_sprache && zustand.sprachen.some(s => s.code === e.letzte_sprache)) { $("#sprache").value = e.letzte_sprache; spracheInfo(); }
  if (e.letzter_modus) { const m = $(`input[name=modus][value=${e.letzter_modus}]`); if (m) { m.checked = true; m.dispatchEvent(new Event("change")); } }
  const st = zustand.status, fehlt = [];
  if (!st.skill) fehlt.push("der Übersetzungs-Skill");
  if (!st.ffmpeg) fehlt.push("ffmpeg");
  if (!st.edge_tts) fehlt.push("edge-tts");
  if (!st.whisper) fehlt.push("faster-whisper");
  const warn = $("#warnleiste");
  if (fehlt.length) { warn.hidden = false; warn.textContent = "Auf diesem Rechner fehlt noch: " + fehlt.join(", ") + ". Siehe LIESMICH.md."; }
  else warnungZeigen();
  pruefen();
  holeAuftraege();
})();
