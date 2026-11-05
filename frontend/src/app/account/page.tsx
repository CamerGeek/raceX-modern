"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import type { CountryCode } from "libphonenumber-js";
import { useAuth } from "../auth-context";
import SiteNavigation from "../site-navigation";
import { parseValidPhoneNumber, PhoneField, usePhonePreferences } from "../phone-field";
import { interpolate, priceLabel } from "../../i18n/format";
import { useI18n } from "../../i18n/provider";

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

function AccountPageContent() {
  const { apiFetch, configured, loading, profile, profileError, refreshProfile, session, signIn, signOut, signUp } = useAuth();
  const { messages, intlLocale } = useI18n();
  const t = messages.account;
  const phonePreferences = usePhonePreferences();
  const [mode, setMode] = useState<"login" | "signup">("signup");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [signupConfirmationEmail, setSignupConfirmationEmail] = useState<string | null>(null);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState<"weekly" | "monthly" | "annual">("monthly");
  const [paymentReturn, setPaymentReturn] = useState(false);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [phoneCountryOverride, setPhoneCountryOverride] = useState<CountryCode | null>(null);
  const phoneCountry = phoneCountryOverride ?? phonePreferences.country;

  const formatDate = (value: string | null) => {
    if (!value) return "—";
    return new Intl.DateTimeFormat(intlLocale, {
      dateStyle: "long",
      timeZone: "Africa/Ouagadougou",
    }).format(new Date(value));
  };

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (new URLSearchParams(window.location.search).get("payment") !== "complete") return;
      setPaymentReturn(true);
      setMessage(t.paymentReturn);
      void refreshProfile();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshProfile, t.paymentReturn]);

  useEffect(() => {
    if (!paymentReturn || profile?.role === "subscriber") return;

    let active = true;
    let attempts = 0;
    let timer: number;
    const refreshUntilActivated = async () => {
      await refreshProfile();
      attempts += 1;
      if (active && attempts < 20) {
        timer = window.setTimeout(refreshUntilActivated, 3000);
      }
    };

    timer = window.setTimeout(refreshUntilActivated, 3000);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [paymentReturn, profile?.role, refreshProfile]);

  async function startCheckout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedPhone = parseValidPhoneNumber(phoneNumber, phoneCountry);
    if (!parsedPhone) {
      setError(t.invalidPhone);
      return;
    }
    setCheckoutBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`${apiUrl}/api/v1/auth/chariow/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          phone_number: parsedPhone.nationalNumber,
          phone_country_code: parsedPhone.countryCode,
          plan: selectedPlan,
        }),
      });
      const result: unknown = await response.json();
      if (!response.ok) {
        const detail =
          typeof result === "object" && result !== null && "detail" in result && typeof result.detail === "string"
            ? result.detail
            : t.checkoutError;
        throw new Error(detail);
      }
      if (!isCheckoutResponse(result) || !result.checkout_url.startsWith("https://")) {
        throw new Error(t.checkoutLinkError);
      }
      window.location.assign(result.checkout_url);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : t.checkoutError);
      setCheckoutBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedPhone = mode === "signup" ? parseValidPhoneNumber(phone, phoneCountry) : null;
    if (mode === "signup" && !parsedPhone) {
      setError(t.invalidPhone);
      return;
    }
    setBusy(true);
    setMessage("");
    setError("");
    try {
      if (mode === "signup") {
        const result = await signUp(email, password, parsedPhone?.internationalNumber ?? "");
        if (result.hasSession) {
          setSignupConfirmationEmail(null);
          setMessage(t.created);
        } else if (result.identityCreated) {
          setSignupConfirmationEmail(email.trim());
        } else {
          setSignupConfirmationEmail(null);
          setMessage(t.signupUnconfirmed);
        }
      } else {
        await signIn(email, password);
        setMessage(t.signedIn);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : t.operationFailed);
    } finally {
      setBusy(false);
    }
  }

  const roleLabel = profile
    ? t.roles[profile.role]
    : "";

  return (
    <main className="shell account-shell">
      <SiteNavigation currentPage="account" />
      <header className="subscriber-header">
        <div>
          <p className="subscriber-eyebrow">{t.eyebrow}</p>
          <h1>{t.title}</h1>
          <p className="subscriber-date">{t.subtitle}</p>
        </div>
      </header>

      {!configured && (
        <section className="subscriber-state subscriber-error" role="alert">
          {t.notConfigured}
        </section>
      )}

      {loading && <section className="subscriber-state" role="status">{t.loading}</section>}

      {!loading && !session && (
        <section className="public-widget account-card">
          {signupConfirmationEmail ? (
            <div className="account-confirmation" role="status" aria-labelledby="account-confirmation-title">
              <p className="public-kicker">{t.confirmationKicker}</p>
              <h2 id="account-confirmation-title">{t.confirmationTitle}</h2>
              <p>
                {t.confirmationBodyBefore} <strong>{signupConfirmationEmail}</strong>. {t.confirmationBodyAfter}
              </p>
              <p className="account-help">{t.confirmationHelp}</p>
              <button
                type="button"
                className="subscriber-refresh"
                onClick={() => {
                  setSignupConfirmationEmail(null);
                  setMode("login");
                  setPassword("");
                }}
              >
                {t.confirmationCta}
              </button>
            </div>
          ) : (
            <>
              <div className="account-mode-switch" aria-label={t.modeSwitchAria}>
                <button type="button" className={mode === "signup" ? "selected" : ""} onClick={() => { setMode("signup"); setError(""); setMessage(""); }}>
                  {t.signupTab}
                </button>
                <button type="button" className={mode === "login" ? "selected" : ""} onClick={() => { setMode("login"); setError(""); setMessage(""); }}>
                  {t.loginTab}
                </button>
              </div>
              <h2>{mode === "signup" ? t.signupTitle : t.loginTitle}</h2>
              <p className="account-card-copy">
                {mode === "signup" ? t.signupCopy : t.loginCopy}
              </p>
              <form className="account-form" onSubmit={submit}>
                <label htmlFor="account-email">{t.email}</label>
                <input id="account-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
                {mode === "signup" && (
                  <PhoneField
                    country={phoneCountry}
                    idPrefix="account-phone"
                    label={t.phone}
                    locale={intlLocale}
                    number={phone}
                    onCountryChange={setPhoneCountryOverride}
                    onNumberChange={setPhone}
                  />
                )}
                <label htmlFor="account-password">{t.password}</label>
                <input id="account-password" type="password" minLength={8} autoComplete={mode === "signup" ? "new-password" : "current-password"} required value={password} onChange={(event) => setPassword(event.target.value)} />
                <p className="account-help">{t.passwordHelp}</p>
                <button className="subscriber-refresh" type="submit" disabled={busy || !configured}>
                  {busy ? t.busy : mode === "signup" ? t.createAccount : t.signIn}
                </button>
              </form>
              {message && <p className="account-message" role="status">{message}</p>}
              {error && <p className="account-error" role="alert">{error}</p>}
            </>
          )}
        </section>
      )}

      {!loading && session && profile && (
        <section className="public-widget account-card">
          <p className="public-kicker">{t.profileKicker}</p>
          <h2>{profile.email}</h2>
          <div className="account-status-grid">
            <div><span>{t.phoneLabel}</span><strong>{profile.phone || t.notProvided}</strong></div>
            <div><span>{t.accessLabel}</span><strong>{roleLabel}</strong></div>
            {profile.role === "demo" && <div><span>{t.demoUntil}</span><strong>{formatDate(profile.demo_expires_at)}</strong></div>}
            {profile.role === "subscriber" && <div><span>{t.subscriptionUntil}</span><strong>{formatDate(profile.subscriber_expires_at)}</strong></div>}
          </div>
          {profile.role !== "admin" && (
            <div className="account-renewal">
              <h3>{profile.role === "subscriber" ? t.renewalSubscriber : t.renewalOther}</h3>
              <p>{t.renewalBody}</p>
              <form className="account-form account-checkout-form" onSubmit={startCheckout}>
                <label htmlFor="checkout-plan">{t.planLabel}</label>
                <select
                  id="checkout-plan"
                  value={selectedPlan}
                  onChange={(event) => {
                    const plan = event.target.value;
                    if (plan === "weekly" || plan === "monthly" || plan === "annual") {
                      setSelectedPlan(plan);
                    }
                  }}
                >
                  <option value="weekly">{interpolate(t.planWeekly, { price: priceLabel(2500, intlLocale) })}</option>
                  <option value="monthly">{interpolate(t.planMonthly, { price: priceLabel(8000, intlLocale) })}</option>
                  <option value="annual">{interpolate(t.planAnnual, { price: priceLabel(80000, intlLocale) })}</option>
                </select>
                <label htmlFor="checkout-first-name">{t.firstName}</label>
                <input id="checkout-first-name" autoComplete="given-name" maxLength={50} required value={firstName} onChange={(event) => setFirstName(event.target.value)} />
                <label htmlFor="checkout-last-name">{t.lastName}</label>
                <input id="checkout-last-name" autoComplete="family-name" maxLength={50} required value={lastName} onChange={(event) => setLastName(event.target.value)} />
                <PhoneField
                  country={phoneCountry}
                  idPrefix="checkout-phone"
                  label={t.phone}
                  locale={intlLocale}
                  number={phoneNumber}
                  onCountryChange={setPhoneCountryOverride}
                  onNumberChange={setPhoneNumber}
                />
                <p className="account-help">{t.phoneHelp}</p>
                <button className="subscriber-refresh account-chariow-button" type="submit" disabled={checkoutBusy}>
                  {checkoutBusy ? t.checkoutBusy : profile.role === "subscriber" ? t.renewOnChariow : t.payOnChariow}
                </button>
              </form>
              {paymentReturn && profile.role !== "subscriber" && (
                <p className="account-payment-pending" role="status">
                  {t.paymentPending}
                </p>
              )}
              {paymentReturn && profile.role === "subscriber" && (
                <p className="account-message" role="status">{interpolate(t.paymentActive, { date: formatDate(profile.subscriber_expires_at) })}</p>
              )}
              {error && <p className="account-error" role="alert">{error}</p>}
              <div className="account-whatsapp-links">
                {whatsappAccounts.map((contact) => (
                  <a key={contact.number} href={`https://wa.me/${contact.number}?text=${encodeURIComponent(t.whatsappMessage)}`} target="_blank" rel="noreferrer">
                    {interpolate(t.whatsappPrefix, { label: contact.label })}
                  </a>
                ))}
              </div>
            </div>
          )}
          <button type="button" className="account-signout" onClick={() => void signOut()}>{t.signOut}</button>
        </section>
      )}

      {!loading && session && !profile && (
        <section className="subscriber-state subscriber-error" role="alert">
          {profileError || t.profileNotLoaded}
        </section>
      )}

      <p className="account-basic-note">{t.basicNote}</p>
      <p><Link href="/">{t.backHome}</Link></p>
    </main>
  );
}

export default function AccountPage() {
  return <AccountPageContent />;
}
