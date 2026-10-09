"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useAuth } from "../auth-context";
import SiteNavigation from "../site-navigation";

const whatsappAccounts = [
  { label: "Moov Burkina", number: "22660354400" },
  { label: "Orange", number: "22674911538" },
];

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "long",
    timeZone: "Africa/Ouagadougou",
  }).format(new Date(value));
}

function AccountPageContent() {
  const { configured, loading, profile, profileError, session, signIn, signOut, signUp } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("signup");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setError("");
    try {
      if (mode === "signup") {
        const hasSession = await signUp(email, password, phone);
        setMessage(hasSession
          ? "Votre compte est créé. Votre accès démo de 7 jours est activé."
          : "Compte créé. Consultez l’e-mail de confirmation : le lien vous ramènera sur cette page pour terminer la connexion.");
      } else {
        await signIn(email, password);
        setMessage("Connexion réussie. Chargement de votre niveau d’accès…");
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "L’opération a échoué.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell account-shell">
      <SiteNavigation currentPage="account" />
      <header className="subscriber-header">
        <div>
          <p className="subscriber-eyebrow">RACEX · COMPTE</p>
          <h1>Votre accès RaceX</h1>
          <p className="subscriber-date">Démo gratuite de 7 jours · abonnement manuel à 5 000 FCFA par mois</p>
        </div>
      </header>

      {!configured && (
        <section className="subscriber-state subscriber-error" role="alert">
          L’authentification n’est pas configurée. L’administrateur doit ajouter les identifiants publics Supabase à la configuration du frontend.
        </section>
      )}

      {loading && <section className="subscriber-state" role="status">Chargement de votre compte…</section>}

      {!loading && !session && (
        <section className="public-widget account-card">
          <div className="account-mode-switch" aria-label="Choisir une action">
            <button type="button" className={mode === "signup" ? "selected" : ""} onClick={() => { setMode("signup"); setError(""); setMessage(""); }}>
              Créer un compte
            </button>
            <button type="button" className={mode === "login" ? "selected" : ""} onClick={() => { setMode("login"); setError(""); setMessage(""); }}>
              Se connecter
            </button>
          </div>
          <h2>{mode === "signup" ? "Commencez vos 7 jours de démo" : "Ravi de vous revoir"}</h2>
          <p className="account-card-copy">
            {mode === "signup"
              ? "La création du compte active automatiquement l’accès aux fonctions abonnés pour 7 jours."
              : "Connectez-vous pour retrouver les droits associés à votre compte."}
          </p>
          <form className="account-form" onSubmit={submit}>
            <label htmlFor="account-email">Adresse e-mail</label>
            <input id="account-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
            {mode === "signup" && (
              <>
                <label htmlFor="account-phone">Numéro de téléphone</label>
                <input id="account-phone" type="tel" autoComplete="tel" pattern="[+0-9(). -]{7,25}" title="Saisissez un numéro de téléphone valide." required value={phone} onChange={(event) => setPhone(event.target.value)} />
              </>
            )}
            <label htmlFor="account-password">Mot de passe</label>
            <input id="account-password" type="password" minLength={8} autoComplete={mode === "signup" ? "new-password" : "current-password"} required value={password} onChange={(event) => setPassword(event.target.value)} />
            <p className="account-help">8 caractères minimum.</p>
            <button className="subscriber-refresh" type="submit" disabled={busy || !configured}>
              {busy ? "Veuillez patienter…" : mode === "signup" ? "Créer mon compte" : "Se connecter"}
            </button>
          </form>
          {message && <p className="account-message" role="status">{message}</p>}
          {error && <p className="account-error" role="alert">{error}</p>}
        </section>
      )}

      {!loading && session && profile && (
        <section className="public-widget account-card">
          <p className="public-kicker">MON COMPTE</p>
          <h2>{profile.email}</h2>
          <div className="account-status-grid">
            <div><span>TÉLÉPHONE</span><strong>{profile.phone || "Non renseigné"}</strong></div>
            <div><span>NIVEAU D’ACCÈS</span><strong>{profile.role === "admin" ? "Administrateur" : profile.role === "subscriber" ? "Abonné" : profile.role === "demo" ? "Démo" : "Accès simple"}</strong></div>
            {profile.role === "demo" && <div><span>DÉMO VALABLE JUSQU’AU</span><strong>{formatDate(profile.demo_expires_at)}</strong></div>}
            {profile.role === "subscriber" && <div><span>ABONNEMENT VALABLE JUSQU’AU</span><strong>{formatDate(profile.subscriber_expires_at)}</strong></div>}
          </div>
          {profile.role === "simple" && (
            <div className="account-renewal">
              <h3>Passer à l’abonnement</h3>
              <p>Après votre démo, contactez l’administrateur pour convenir du moyen de transfert. L’abonnement est activé manuellement après confirmation du paiement de 5 000 FCFA pour un mois.</p>
              <div className="account-whatsapp-links">
                {whatsappAccounts.map((contact) => (
                  <a key={contact.number} href={`https://wa.me/${contact.number}?text=${encodeURIComponent("Bonjour, je souhaite activer ou renouveler mon abonnement RaceX à 5 000 FCFA.")}`} target="_blank" rel="noreferrer">
                    Contacter sur WhatsApp · {contact.label}
                  </a>
                ))}
              </div>
            </div>
          )}
          <button type="button" className="account-signout" onClick={() => void signOut()}>Se déconnecter</button>
        </section>
      )}

      {!loading && session && !profile && (
        <section className="subscriber-state subscriber-error" role="alert">
          {profileError || "Votre profil n’a pas pu être chargé."}
        </section>
      )}

      <p className="account-basic-note">L’accueil public reste consultable sans compte. Aucun paiement n’est collecté dans l’application.</p>
      <p><Link href="/">Retour à l’accueil</Link></p>
    </main>
  );
}

export default function AccountPage() {
  return <AccountPageContent />;
}
