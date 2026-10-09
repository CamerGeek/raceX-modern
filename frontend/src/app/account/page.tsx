"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useAuth } from "../auth-context";
import SiteNavigation from "../site-navigation";

const whatsappAccounts = [
  { label: "Moov Burkina", number: "22660354400" },
  { label: "Orange", number: "22674911538" },
];
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function isCheckoutResponse(value: unknown): value is { checkout_url: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    "checkout_url" in value &&
    typeof value.checkout_url === "string"
  );
}

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "long",
    timeZone: "Africa/Ouagadougou",
  }).format(new Date(value));
}

function AccountPageContent() {
  const { apiFetch, configured, loading, profile, profileError, refreshProfile, session, signIn, signOut, signUp } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("signup");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [paymentReturn, setPaymentReturn] = useState(false);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("payment") !== "complete") return;
    setPaymentReturn(true);
    setMessage("Retour de Chariow détecté. RaceX vérifie la confirmation du paiement avant d’activer votre abonnement.");
    void refreshProfile();
  }, [refreshProfile]);

  async function startCheckout() {
    setCheckoutBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`${apiUrl}/api/v1/auth/chariow/checkout`, { method: "POST" });
      const result: unknown = await response.json();
      if (!response.ok) {
        const detail =
          typeof result === "object" && result !== null && "detail" in result && typeof result.detail === "string"
            ? result.detail
            : "Impossible de démarrer le paiement Chariow.";
        throw new Error(detail);
      }
      if (!isCheckoutResponse(result) || !result.checkout_url.startsWith("https://")) {
        throw new Error("Chariow n’a pas renvoyé de lien de paiement valide.");
      }
      window.location.assign(result.checkout_url);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Impossible de démarrer le paiement Chariow.");
      setCheckoutBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setError("");
    try {
      if (mode === "signup") {
        const result = await signUp(email, password, phone);
        setMessage(result.hasSession
          ? "Votre compte est créé. Votre accès démo de 7 jours est activé."
          : result.identityCreated
            ? "Votre demande d’inscription a été acceptée. Si la confirmation par e-mail est activée, consultez votre boîte de réception et vos courriers indésirables."
            : "Supabase n’a pas confirmé la création d’un nouveau compte. Si vous avez déjà un compte, essayez de vous connecter ou réinitialisez le mot de passe. Sinon, vérifiez que l’inscription par e-mail est activée dans Supabase.");
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
          <p className="subscriber-date">Démo gratuite de 7 jours · paiement à renouveler chaque mois</p>
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
          {profile.role !== "admin" && (
            <div className="account-renewal">
              <h3>{profile.role === "subscriber" ? "Renouveler votre accès" : "Passer à l’abonnement"}</h3>
              <p>
                Payez les 10 000 FCFA sur Chariow. Chaque paiement confirmé ajoute un mois d’accès RaceX. Le paiement est traité de façon sécurisée par Chariow.
              </p>
              <button className="subscriber-refresh account-chariow-button" type="button" onClick={() => void startCheckout()} disabled={checkoutBusy}>
                {checkoutBusy ? "Redirection vers Chariow…" : profile.role === "subscriber" ? "Renouveler sur Chariow" : "Payer sur Chariow"}
              </button>
              {paymentReturn && profile.role !== "subscriber" && (
                <p className="account-payment-pending" role="status">
                  Votre retour ne confirme pas le paiement. Si vous venez de payer, patientez quelques instants puis actualisez votre compte.
                </p>
              )}
              {paymentReturn && profile.role === "subscriber" && (
                <p className="account-message" role="status">Votre accès abonné est actif jusqu’au {formatDate(profile.subscriber_expires_at)}.</p>
              )}
              {error && <p className="account-error" role="alert">{error}</p>}
              <div className="account-whatsapp-links">
                {whatsappAccounts.map((contact) => (
                  <a key={contact.number} href={`https://wa.me/${contact.number}?text=${encodeURIComponent("Bonjour, j’ai une question concernant le paiement ou l’activation de mon abonnement RaceX à 10 000 FCFA.")}`} target="_blank" rel="noreferrer">
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

      <p className="account-basic-note">L’accueil public reste consultable sans compte. Les paiements sont traités sur Chariow.</p>
      <p><Link href="/">Retour à l’accueil</Link></p>
    </main>
  );
}

export default function AccountPage() {
  return <AccountPageContent />;
}
