import { Link, usePage } from '@inertiajs/react';
import {
    CheckCircle,
    EnvelopeSimple,
    FacebookLogo,
    ShieldCheck,
    WhatsappLogo,
} from '@phosphor-icons/react';

import Footer from '@/components/footer';
import Navbar from '@/components/navbar';

interface FinalizarSettings {
    heading: string;
    subheading: string;
    contact_question: string;
    tna: string;
    tea: string;
    tnm: string;
    cft: string;
    terms_url: string;
    contact_email: string;
    whatsapp_url: string;
    facebook_url: string;
}

interface Solicitud {
    monto: string;
    cuotas: string;
    nro: string;
}

interface PageProps {
    settings: FinalizarSettings;
    solicitud: Solicitud;
    [key: string]: unknown;
}

function formatMonto(monto: string): string {
    if (!monto) return '';
    const num = parseFloat(monto);
    if (isNaN(num)) return monto;
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: 'ARS',
        maximumFractionDigits: 0,
    }).format(num);
}

function RateItem({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex items-center justify-between gap-4 border-b border-gray-100 py-2 last:border-0">
            <span className="text-sm text-gray-600">{label}</span>
            <span className="text-sm font-semibold text-gray-800">
                {value ? `${value}%` : <span className="text-gray-400">—</span>}
            </span>
        </div>
    );
}

export default function Finalizar() {
    const { settings, solicitud } = usePage<PageProps>().props;

    const hasLoanData = solicitud.monto || solicitud.cuotas || solicitud.nro;

    return (
        <div className="flex min-h-screen flex-col bg-gray-50">
            <Navbar activeTab="unset" setActiveTab={() => {}} />

            <main className="flex flex-1 flex-col items-center justify-center px-4 py-16 sm:px-6">
                <div className="w-full max-w-lg">
                    {/* ── Header ── */}
                    <div className="mb-10 text-center">
                        <p className="mb-2 text-xs font-bold tracking-widest text-emerald-600 uppercase">
                            Acepta tu Crédito
                        </p>
                        <h1 className="text-4xl font-extrabold tracking-tight text-gray-900">
                            {settings.heading || 'Termina tu Solicitud'}
                        </h1>
                        <p className="mt-4 text-base text-gray-500">
                            {settings.subheading ||
                                'Su préstamo será descontado de la siguiente forma:'}
                        </p>
                    </div>

                    {/* ── Loan Summary Card ── */}
                    <div className="mb-6 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
                        {/* Cuotas / Monto highlight */}
                        <div className="bg-linear-to-br from-emerald-50 to-white px-8 py-8 text-center">
                            {hasLoanData ? (
                                <>
                                    {solicitud.cuotas && solicitud.monto ? (
                                        <p className="text-2xl font-light text-gray-700">
                                            EN{' '}
                                            <span className="font-extrabold text-emerald-600">
                                                {solicitud.cuotas} CUOTAS
                                            </span>{' '}
                                            DE{' '}
                                            <span className="font-extrabold text-emerald-600">
                                                {formatMonto(solicitud.monto)}
                                            </span>
                                        </p>
                                    ) : solicitud.cuotas ? (
                                        <p className="text-2xl font-light text-gray-700">
                                            EN{' '}
                                            <span className="font-extrabold text-emerald-600">
                                                {solicitud.cuotas} CUOTAS
                                            </span>
                                        </p>
                                    ) : solicitud.monto ? (
                                        <p className="text-2xl font-light text-gray-700">
                                            Monto:{' '}
                                            <span className="font-extrabold text-emerald-600">
                                                {formatMonto(solicitud.monto)}
                                            </span>
                                        </p>
                                    ) : null}
                                </>
                            ) : (
                                <p className="text-lg font-semibold text-gray-400">
                                    EN{' '}
                                    <span className="text-emerald-500">
                                        CUOTAS
                                    </span>{' '}
                                    DE
                                </p>
                            )}
                        </div>

                        <div className="divide-y divide-gray-100 px-8 py-4">
                            {/* Monto row */}
                            <div className="flex items-center justify-between py-3">
                                <span className="text-sm font-medium text-gray-500">
                                    Monto de tu Crédito
                                </span>
                                <span className="text-base font-bold text-gray-800">
                                    {solicitud.monto ? (
                                        formatMonto(solicitud.monto)
                                    ) : (
                                        <span className="text-gray-300">—</span>
                                    )}
                                </span>
                            </div>

                            {/* Nro Solicitud row */}
                            <div className="flex items-center justify-between py-3">
                                <span className="text-sm font-medium text-gray-500">
                                    Número de Solicitud
                                </span>
                                <span className="text-base font-bold text-gray-800">
                                    {solicitud.nro ? (
                                        `#${solicitud.nro}`
                                    ) : (
                                        <span className="text-gray-300">—</span>
                                    )}
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* ── Verify Button ── */}
                    <div className="mb-6 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
                        <div className="flex items-center gap-0">
                            {/* Left: checkbox illustration */}
                            <div className="flex items-center justify-center border-r border-gray-200 bg-gray-50 px-6 py-5">
                                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white shadow-inner">
                                    <ShieldCheck
                                        size={24}
                                        className="text-emerald-500"
                                        weight="duotone"
                                    />
                                </div>
                            </div>
                            {/* Right: verify button */}
                            <button
                                type="button"
                                className="flex flex-1 items-center justify-center gap-2 bg-[#4a7cdc] py-5 text-sm font-semibold text-white transition-opacity hover:opacity-90 active:opacity-80"
                            >
                                <CheckCircle size={18} weight="bold" />
                                Verify me
                            </button>
                        </div>
                    </div>

                    {/* ── Tasas / Terms ── */}
                    <div className="mb-6 rounded-2xl border border-gray-200 bg-white px-6 py-6 shadow-sm">
                        <div className="mb-4 flex items-center justify-between">
                            <p className="text-xs font-bold tracking-widest text-gray-500 uppercase">
                                Condiciones Financieras
                            </p>
                            {settings.terms_url && (
                                <Link
                                    href={settings.terms_url}
                                    className="text-xs font-semibold text-emerald-600 underline underline-offset-2 transition-colors hover:text-emerald-700"
                                >
                                    Términos y condiciones
                                </Link>
                            )}
                        </div>

                        <div>
                            <RateItem
                                label="Tasa Nominal Anual (TNA)"
                                value={settings.tna}
                            />
                            <RateItem
                                label="Tasa Efectiva Anual (TEA)"
                                value={settings.tea}
                            />
                            <RateItem
                                label="Tasa Nominal Mensual (TNM)"
                                value={settings.tnm}
                            />
                            <RateItem
                                label="Costo Financiero Total Efectivo Anual (CFT)"
                                value={settings.cft}
                            />
                        </div>
                    </div>

                    {/* ── Contact Section ── */}
                    <div className="rounded-2xl border border-gray-200 bg-white px-6 py-6 shadow-sm">
                        <p className="mb-5 text-center text-sm font-semibold text-gray-700">
                            {settings.contact_question ||
                                '¿Tiene otra consulta para hacernos?'}
                        </p>

                        <div className="flex flex-col gap-3">
                            {settings.contact_email && (
                                <a
                                    href={`mailto:${settings.contact_email}`}
                                    className="flex items-center gap-3 rounded-xl border border-gray-100 bg-gray-50 px-4 py-3 text-sm text-gray-700 transition-all hover:border-emerald-200 hover:bg-emerald-50 hover:text-emerald-700"
                                >
                                    <EnvelopeSimple
                                        size={18}
                                        className="shrink-0 text-emerald-600"
                                        weight="duotone"
                                    />
                                    <span>
                                        Escribinos por mail a{' '}
                                        <strong>
                                            {settings.contact_email}
                                        </strong>
                                    </span>
                                </a>
                            )}

                            {settings.whatsapp_url && (
                                <a
                                    href={settings.whatsapp_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center gap-3 rounded-xl border border-gray-100 bg-gray-50 px-4 py-3 text-sm text-gray-700 transition-all hover:border-green-200 hover:bg-green-50 hover:text-green-700"
                                >
                                    <WhatsappLogo
                                        size={18}
                                        className="shrink-0 text-green-500"
                                        weight="fill"
                                    />
                                    <span>
                                        Contáctanos por{' '}
                                        <strong>WhatsApp</strong>
                                    </span>
                                </a>
                            )}

                            {settings.facebook_url && (
                                <a
                                    href={settings.facebook_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center gap-3 rounded-xl border border-gray-100 bg-gray-50 px-4 py-3 text-sm text-gray-700 transition-all hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
                                >
                                    <FacebookLogo
                                        size={18}
                                        className="shrink-0 text-blue-600"
                                        weight="fill"
                                    />
                                    <span>
                                        o a nuestro{' '}
                                        <strong>Facebook Messenger</strong>
                                    </span>
                                </a>
                            )}
                        </div>
                    </div>
                </div>
            </main>

            <Footer />
        </div>
    );
}
