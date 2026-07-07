import { useEffect, useMemo, useState } from "react";
import { api, ReferralSettings } from "../api";
import { Select } from "../components/Select";
import { Switch } from "../components/Switch";

type Milestone = { count: number; bonus: number };
type Draft = {
  enabled: boolean;
  reward_credits: number;
  daily_invite_limit: number;
  reward_on_register: boolean;
  require_subscription: boolean;
  invitee_reward_credits: number;
  milestones: Milestone[];   // sorted by count for stable dirty-compare
  age_fraud_enabled: boolean;
  min_referred_age_hours: number;
};
const milestonesToList = (m: Record<string, number>): Milestone[] =>
  Object.entries(m ?? {}).map(([c, b]) => ({ count: Number(c), bonus: Number(b) }))
    .sort((a, b) => a.count - b.count);
const milestonesToMap = (list: Milestone[]): Record<string, number> => {
  const out: Record<string, number> = {};
  for (const { count, bonus } of list) if (count > 0 && bonus > 0) out[String(count)] = bonus;
  return out;
};
const draftOf = (s: ReferralSettings): Draft => ({
  enabled: s.enabled, reward_credits: s.reward_credits, daily_invite_limit: s.daily_invite_limit,
  reward_on_register: s.reward_on_register, require_subscription: s.require_subscription,
  invitee_reward_credits: s.invitee_reward_credits, milestones: milestonesToList(s.milestones),
  age_fraud_enabled: s.age_fraud_enabled, min_referred_age_hours: s.min_referred_age_hours,
});

export function Referrals() {
  const [s, setS] = useState<ReferralSettings | null>(null);
  const [d, setD] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  function apply(data: ReferralSettings) { setS(data); setD(draftOf(data)); }
  const load = () => api.referralSettings().then(apply).catch((e) => setMsg(String(e)));
  useEffect(() => { load(); }, []);

  const dirty = useMemo(() => s && d && JSON.stringify(draftOf(s)) !== JSON.stringify(d), [s, d]);

  async function save() {
    if (!d || !s) return;
    if (s.enabled && !d.enabled && !confirm("Отключить реферальную программу? Новые приглашения перестанут вознаграждаться.")) return;
    setSaving(true);
    try {
      const data = await api.setReferralSettings({
        enabled: d.enabled, reward_credits: Math.max(0, d.reward_credits),
        daily_invite_limit: Math.max(0, d.daily_invite_limit),
        reward_on_register: d.reward_on_register, require_subscription: d.require_subscription,
        invitee_reward_credits: Math.max(0, d.invitee_reward_credits),
        milestones: milestonesToMap(d.milestones),
        age_fraud_enabled: d.age_fraud_enabled,
        min_referred_age_hours: Math.max(0, d.min_referred_age_hours),
      });
      apply(data);
      setMsg("✅ Настройки сохранены");
    } catch (e) { setMsg(String(e)); }
    finally { setSaving(false); }
  }

  const kpi = useMemo(() => {
    const st = s?.stats;
    const total = st?.total_referrals ?? 0;
    const rewarded = st?.rewarded ?? 0;
    return { total, rewarded, pending: Math.max(0, total - rewarded), conv: total ? Math.round((rewarded / total) * 100) : 0 };
  }, [s]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((p) => (p ? { ...p, [k]: v } : p));

  return (
    <div>
      <h1 className="page-title">Реферальная программа</h1>
      <p className="page-sub">Условия вознаграждения, лимиты, антифрод и статистика приглашений.</p>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>{msg}
          <button className="btn ghost sm" onClick={() => setMsg("")}>×</button>
        </p>
      )}

      {!d || !s ? (
        <div className="panel"><div className="loading">Загрузка…</div></div>
      ) : (
        <div className="page-stack">
          <div className="metrics">
            <Metric icon="group" label="Всего рефералов" value={kpi.total} />
            <Metric icon="paid" label="Вознаграждено" value={kpi.rewarded} tone="purple" />
            <Metric icon="hourglass_top" label="Ожидает награды" value={kpi.pending} tone={kpi.pending > 0 ? "danger" : undefined} />
            <Metric icon="percent" label="Конверсия в награду" value={kpi.conv} suffix="%" />
          </div>

          <div className="panel">
            <div className="section-head">
              <div className="panel-title" style={{ margin: 0 }}>
                <span className="ms sm">tune</span> Настройки программы
                <span className={"pill " + (d.enabled ? "ok" : "muted")}>{d.enabled ? "включена" : "выключена"}</span>
              </div>
              <div className="form-row">
                {dirty && <span className="pill warn">● не сохранено</span>}
                <button className="btn" disabled={!dirty || saving} onClick={save}>
                  <span className="ms sm">save</span> {saving ? "Сохранение…" : "Сохранить"}
                </button>
              </div>
            </div>

            <div className="panel-title sm" style={{ marginBottom: "var(--sp-3)" }}>Общие</div>
            <div className="form-row" style={{ justifyContent: "space-between", marginBottom: "var(--sp-4)" }}>
              <Switch checked={d.enabled} onChange={(v) => set("enabled", v)} label="Программа включена" />
              <span className="cfg-hint" style={{ maxWidth: 420 }}>
                При выключении новые приглашения не вознаграждаются. Реф-ссылки продолжают работать, но награда не начисляется.
              </span>
            </div>

            <div className="panel-title sm" style={{ margin: "var(--sp-2) 0 var(--sp-3)" }}>Вознаграждение</div>
            <div className="form-grid">
              <div className="cfg-field">
                <span className="cfg-cap">Награда рефереру, ✨</span>
                {/* FIX: AUDIT12-M13/M14 - max 10_000_000 ceiling on referral reward credits. */}
                <input type="number" min={0} max={10_000_000} value={d.reward_credits}
                  aria-label="Награда пригласившему"
                  onChange={(e) => set("reward_credits", Math.max(0, Number(e.target.value) || 0))} />
                <p className="cfg-hint">Кредиты пригласившему, когда выполнено условие начисления (ниже).</p>
              </div>
              <div className="cfg-field">
                <span className="cfg-cap">Условие начисления</span>
                <Select width="100%" ariaLabel="Условие начисления"
                  value={d.reward_on_register ? "register" : "purchase"}
                  onChange={(v) => set("reward_on_register", v === "register")}
                  options={[
                    { value: "register", label: "За регистрацию приглашённого" },
                    { value: "purchase", label: "За первую оплату приглашённого" },
                  ]} />
                <p className="cfg-hint">«За оплату» снижает фрод, но даёт меньше начислений, чем «за регистрацию».</p>
              </div>
              <div className="cfg-field">
                <span className="cfg-cap">Бонус приглашённому, ✨</span>
                {/* FIX: AUDIT12-M13/M14 - max 10_000_000 ceiling on invitee reward. */}
                <input type="number" min={0} max={10_000_000} value={d.invitee_reward_credits}
                  aria-label="Награда приглашённому"
                  onChange={(e) => set("invitee_reward_credits", Math.max(0, Number(e.target.value) || 0))} />
                <p className="cfg-hint">Двусторонняя программа: приветственный бонус самому приглашённому при переходе по ссылке. 0 = выключено.</p>
              </div>
            </div>

            <div className="panel-title sm" style={{ margin: "var(--sp-4) 0 var(--sp-3)" }}>Этапные бонусы рефереру</div>
            <p className="cfg-hint" style={{ marginTop: 0 }}>
              Разовый доп-бонус, когда число приглашённых пересекает порог (геймификация). Каждый порог начисляется один раз.
            </p>
            {d.milestones.length > 0 && (
              <div className="form-row" style={{ flexWrap: "wrap", gap: "var(--sp-2)", marginBottom: "var(--sp-2)" }}>
                {d.milestones.map((m, i) => (
                  <div key={i} className="form-row" style={{ gap: 6, alignItems: "center" }}>
                    {/* FIX: AUDIT12-M14 - max 10000 ceiling on milestone count. */}
                    <input type="number" min={1} max={10000} style={{ width: 90 }} value={m.count} aria-label="Порог приглашений"
                      onChange={(e) => set("milestones", d.milestones.map((x, j) =>
                        j === i ? { ...x, count: Math.max(1, Number(e.target.value) || 1) } : x))} />
                    <span className="muted">→ ✨</span>
                    {/* FIX: AUDIT12-M14 - max 10_000_000 ceiling on milestone bonus. */}
                    <input type="number" min={1} max={10_000_000} style={{ width: 100 }} value={m.bonus} aria-label="Бонус"
                      onChange={(e) => set("milestones", d.milestones.map((x, j) =>
                        j === i ? { ...x, bonus: Math.max(1, Number(e.target.value) || 1) } : x))} />
                    <button className="btn ghost sm danger" title="Удалить порог"
                      onClick={() => set("milestones", d.milestones.filter((_, j) => j !== i))}>
                      <span className="ms sm">delete</span>
                    </button>
                  </div>
                ))}
              </div>
            )}
            <button className="btn ghost sm" onClick={() => set("milestones",
              [...d.milestones, { count: (d.milestones[d.milestones.length - 1]?.count ?? 0) + 5, bonus: 100 }])}>
              <span className="ms sm">add</span> Добавить порог
            </button>

            <div className="panel-title sm" style={{ margin: "var(--sp-4) 0 var(--sp-3)" }}>Ограничения</div>
            <div className="form-grid">
              <div className="cfg-field">
                <span className="cfg-cap">Лимит приглашений в день</span>
                {/* FIX: AUDIT12-M14 - max 10000 ceiling on daily invite limit. */}
                <input type="number" min={0} max={10000} value={d.daily_invite_limit}
                  aria-label="Дневной лимит приглашений"
                  onChange={(e) => set("daily_invite_limit", Math.max(0, Number(e.target.value) || 0))} />
                <p className="cfg-hint">Сколько приглашений в сутки засчитывается одному пользователю. 0 = без лимита.</p>
              </div>
            </div>

            <div className="panel-title sm" style={{ margin: "var(--sp-4) 0 var(--sp-3)" }}>Антифрод</div>
            <div className="form-row" style={{ marginBottom: "var(--sp-3)" }}>
              <Switch checked={d.require_subscription} onChange={(v) => set("require_subscription", v)}
                label="Требовать подписку на канал" />
            </div>
            <div className="form-row" style={{ marginBottom: "var(--sp-3)" }}>
              <Switch checked={d.age_fraud_enabled} onChange={(v) => set("age_fraud_enabled", v)}
                label="Удержание награды по возрасту аккаунта" />
            </div>
            <div className="form-grid">
              <div className="cfg-field">
                <span className="cfg-cap">Мин. возраст приглашённого, ч</span>
                {/* FIX: AUDIT12-M14 - max 87600 ceiling on min referred age (1 year in hours). */}
                <input type="number" min={0} max={87600} value={d.min_referred_age_hours} disabled={!d.age_fraud_enabled}
                  aria-label="Минимальный возраст реферала, часы"
                  onChange={(e) => set("min_referred_age_hours", Math.max(0, Number(e.target.value) || 0))} />
                <p className="cfg-hint">Награда удерживается, пока аккаунт приглашённого младше указанного возраста (защита от ферм фейк-аккаунтов).</p>
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-title"><span className="ms sm">leaderboard</span> Топ рефереров</div>
            {(s.stats?.top_referrers ?? []).length === 0 ? (
              <div className="empty-state">
                <div className="es-icon"><span className="ms">group_add</span></div>
                <p className="es-title">Пока нет приглашений</p>
                <p className="es-desc">Как только пользователи начнут приглашать друзей по реф-ссылке, здесь появится рейтинг самых активных рефереров.</p>
              </div>
            ) : (
              <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
                <table className="tbl">
                  <thead><tr><th style={{ width: 48 }}>#</th><th>User ID</th><th>Приглашено</th></tr></thead>
                  <tbody>
                    {(() => {
                      const max = Math.max(1, ...(s.stats?.top_referrers ?? []).map((r) => r.count));
                      return (s.stats?.top_referrers ?? []).map((r, i) => (
                        <tr key={r.user_id}>
                          <td className="muted">{i + 1}</td>
                          <td className="code-key">{r.user_id}</td>
                          <td>
                            <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 140 }}>
                              <div style={{ flex: 1, height: 6, borderRadius: 999, background: "var(--panel-2)", overflow: "hidden", maxWidth: 160 }}>
                                <div style={{ height: "100%", width: (r.count / max) * 100 + "%", background: "var(--accent)" }} />
                              </div>
                              <b style={{ fontVariantNumeric: "tabular-nums" }}>{r.count.toLocaleString("ru")}</b>
                            </div>
                          </td>
                        </tr>
                      ));
                    })()}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ icon, label, value, suffix, tone }: {
  icon: string; label: string; value: number; suffix?: string; tone?: "purple" | "danger";
}) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span><span className="ms sm">{icon}</span></div>
      <div><div className="num">{value.toLocaleString("ru")}{suffix && <small>{suffix}</small>}</div></div>
    </div>
  );
}
