"use client";

import { useCallback, useEffect, useState } from "react";
import AccessGate from "../../access-gate";
import { useAuth } from "../../auth-context";
import SiteNavigation from "../../site-navigation";

type Account = {
  id: string;
  email: string;
  phone: string | null;
  role: "demo" | "subscriber" | "admin" | "simple";
  effective_role: "demo" | "subscriber" | "admin" | "simple";
  demo_expires_at: string | null;
  subscriber_expires_at: string | null;
  created_at: string;
};

type SubscriptionPlan = "weekly" | "monthly" | "annual";

const subscriptionPlans: { value: SubscriptionPlan; label: string; action: string }[] = [
  { value: "weekly", label: "Hebdomadaire · 2 500 FCFA · 7 jours", action: "une semaine" },
  { value: "monthly", label: "Mensuelle · 8 000 FCFA · 1 mois", action: "un mois" },
  { value: "annual", label: "Annuelle · 80 000 FCFA · 1 an", action: "un an" },
];

function displayDate(value: string | null) {
  return value
    ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeZone: "Africa/Ouagadougou" }).format(new Date(value))
    : "—";
}

function AdminUsersContent() {
  const { apiFetch } = useAuth();
  const [users, setUsers] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeUser, setActiveUser] = useState("");
  const [selectedPlans, setSelectedPlans] = useState<Record<string, SubscriptionPlan>>({});

  const loadUsers = useCallback(async () => {
    try {
      const response = await apiFetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/auth/admin/users`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Impossible de charger les comptes.");
      setUsers(payload.users as Account[]);
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Impossible de charger les comptes.");
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadUsers(), 0);
    return () => window.clearTimeout(timer);
  }, [loadUsers]);

  async function promote(userId: string, plan: SubscriptionPlan) {
    setActiveUser(userId);
    setError("");
    try {
      const response = await apiFetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/auth/admin/promote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, plan }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Impossible d’activer l’abonnement.");
      await loadUsers();
    } catch (promotionError) {
      setError(promotionError instanceof Error ? promotionError.message : "Impossible d’activer l’abonnement.");
    } finally {
      setActiveUser("");
    }
  }

  return (
    <main className="shell subscriber-shell">
      <SiteNavigation currentPage="user-admin" />
      <header className="subscriber-header">
        <div>
          <p className="subscriber-eyebrow">ADMINISTRATION</p>
          <h1>Gestion des comptes</h1>
          <p className="subscriber-date">Après confirmation du transfert, choisissez la durée à accorder ou à ajouter à l’accès existant.</p>
        </div>
        <button type="button" className="subscriber-refresh" onClick={() => { setLoading(true); void loadUsers(); }}>Actualiser</button>
      </header>
      {error && <section className="subscriber-state subscriber-error" role="alert">{error}</section>}
      <section className="public-widget admin-users-panel">
        {loading ? <p className="subscriber-state" role="status">Chargement des comptes…</p> : users.length === 0 ? (
          <p className="subscriber-state">Aucun compte inscrit.</p>
        ) : (
          <div className="admin-users-table-wrap">
            <table className="admin-users-table">
              <thead><tr><th>Compte</th><th>Téléphone</th><th>Accès</th><th>Démo jusqu’au</th><th>Abonnement jusqu’au</th><th>Action</th></tr></thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>{user.email}</td>
                    <td>{user.phone || "—"}</td>
                    <td><span className={`account-role-badge role-${user.effective_role}`}>{user.effective_role}</span></td>
                    <td>{displayDate(user.demo_expires_at)}</td>
                    <td>{displayDate(user.subscriber_expires_at)}</td>
                    <td>
                      {user.role === "admin" ? "Administrateur" : (
                        <div className="admin-plan-actions">
                          <select
                            aria-label={`Durée d’abonnement pour ${user.email}`}
                            value={selectedPlans[user.id] ?? "monthly"}
                            onChange={(event) => {
                              const plan = event.target.value;
                              if (plan === "weekly" || plan === "monthly" || plan === "annual") {
                                setSelectedPlans((current) => ({ ...current, [user.id]: plan }));
                              }
                            }}
                            disabled={activeUser === user.id}
                          >
                            {subscriptionPlans.map(({ value, label }) => (
                              <option key={value} value={value}>{label}</option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className="admin-promote-button"
                            onClick={() => void promote(user.id, selectedPlans[user.id] ?? "monthly")}
                            disabled={activeUser === user.id}
                          >
                            {activeUser === user.id
                              ? "Activation…"
                              : `Activer ${subscriptionPlans.find(({ value }) => value === (selectedPlans[user.id] ?? "monthly"))?.action}`}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <p className="account-basic-note">La durée choisie s’ajoute à la date de fin existante, ou démarre dès aujourd’hui si l’accès est expiré.</p>
    </main>
  );
}

export default function AdminUsersPage() {
  return <AccessGate allowedRoles={["admin"]}><AdminUsersContent /></AccessGate>;
}
