import React from 'react';
import { createRoot } from 'react-dom/client';
import '../css/app.css';

const rootElement = document.getElementById('app');

const initialPayload = rootElement?.dataset.payload ? JSON.parse(rootElement.dataset.payload) : { branding: {}, tools: [] };

const currencyFormatter = new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 2,
});

const icons = {
    'credit-path': (
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
            <path d="M5 8.5H23" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <rect x="4" y="6" width="20" height="16" rx="4" stroke="currentColor" strokeWidth="2" />
            <path d="M8 17H14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <path d="M18 15.5L20 17.5L24 13.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    ),
    plus: (
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
            <rect x="4" y="4" width="20" height="20" rx="6" stroke="currentColor" strokeWidth="2" strokeDasharray="4 4" />
            <path d="M14 9V19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <path d="M9 14H19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
    ),
};

function App({ branding, tools }) {
    const featuredTool = tools[0] ?? null;
    const [cuil, setCuil] = React.useState('');
    const [loading, setLoading] = React.useState(false);
    const [result, setResult] = React.useState(null);
    const [error, setError] = React.useState('');

    const handleSubmit = async (event) => {
        event.preventDefault();

        if (!featuredTool?.endpoint) {
            setError('La herramienta todavia no tiene un endpoint configurado.');
            return;
        }

        setLoading(true);
        setError('');
        setResult(null);

        try {
            const response = await fetch(featuredTool.endpoint, {
                method: 'POST',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ cuil }),
            });

            const payload = await response.json().catch(() => ({}));

            if (!response.ok) {
                throw new Error(payload.message ?? 'La consulta no pudo completarse.');
            }

            setResult(payload);
        } catch (submitError) {
            setError(submitError.message);
        } finally {
            setLoading(false);
        }
    };

    const resultTone = getResultTone(result, error);

    return (
        <div className="shell">
            <section className="hero">
                <div className="hero__topbar">
                    <div className="brand">
                        <div className="brand__mark">RU</div>
                        <div>
                            <p className="brand__eyebrow">{branding.eyebrow}</p>
                            <p className="brand__title">{branding.title}</p>
                        </div>
                    </div>
                    <a className="hero__cta" href={branding.support_url} target="_blank" rel="noreferrer">
                        {branding.support_label}
                    </a>
                </div>

                <div className="hero__body">
                    <div>
                        <p className="hero__eyebrow">Hub operativo</p>
                        <h1 className="hero__title">{branding.headline}</h1>
                        <p className="hero__description">{branding.description}</p>
                    </div>
                    <div className="hero__stats">
                        <article className="stat-card">
                            <p className="hero__eyebrow">Disponibles hoy</p>
                            <strong>{tools.length.toString().padStart(2, '0')} herramienta activa</strong>
                        </article>
                        <article className="stat-card">
                            <p className="hero__eyebrow">Modo de alta</p>
                            <strong>Catalogo versionado en Git</strong>
                        </article>
                    </div>
                </div>
            </section>

            <div className="content-grid">
                <section className="panel tool-panel">
                    <div className="tool-panel__header">
                        <div>
                            <p className="section__eyebrow">Primera herramienta</p>
                            <h2 className="tool-panel__title">{featuredTool?.title}</h2>
                            <p className="tool-panel__description">{featuredTool?.description}</p>
                        </div>
                        <span className="status-chip status-chip--live">Activo</span>
                    </div>

                    <div className="tool-grid">
                        {tools.map((tool) => (
                            <article className="tool-card tool-card--active" key={tool.id}>
                                <div className="tool-card__icon">{icons[tool.icon] ?? icons.plus}</div>
                                <h3 className="tool-card__title">{tool.title}</h3>
                                <p className="tool-card__description">{tool.helper}</p>
                                <div className="tool-card__footer">
                                    <span className="tool-card__category">{tool.category}</span>
                                    <span className="status-chip status-chip--live">Listo</span>
                                </div>
                            </article>
                        ))}

                        <article className="tool-card">
                            <div className="tool-card__icon">{icons.plus}</div>
                            <h3 className="tool-card__title">Proxima herramienta</h3>
                            <p className="tool-card__description">Este espacio ya queda preparado para sumar nuevas automatizaciones, reportes o accesos internos.</p>
                            <div className="tool-card__footer">
                                <span className="tool-card__category">Alta manual</span>
                                <span className="status-chip status-chip--soon">Proximamente</span>
                            </div>
                        </article>
                    </div>
                </section>

                <aside className="panel form-panel">
                    <p className="section__eyebrow">Consulta online</p>
                    <h2 className="form-panel__title">Consulta Renovacion Cruz del Eje</h2>
                    <p className="form-panel__copy">Ingresa el CUIL del socio para consultar el estado actual de renovacion directamente contra el flujo de analisis de credito.</p>

                    <form onSubmit={handleSubmit}>
                        <div className="field">
                            <label htmlFor="cuil">CUIL</label>
                            <input
                                id="cuil"
                                name="cuil"
                                placeholder="20-12345678-3"
                                value={cuil}
                                onChange={(event) => setCuil(event.target.value)}
                                autoComplete="off"
                            />
                            <div className="field__hint">Acepta CUIL con o sin guiones. La consulta no guarda datos en base por ahora.</div>
                        </div>

                        <div className="actions">
                            <button className="button button--primary" disabled={loading} type="submit">
                                {loading ? 'Consultando...' : featuredTool?.actionLabel ?? 'Consultar'}
                            </button>
                            <button className="button button--ghost" type="button" onClick={() => { setCuil(''); setResult(null); setError(''); }}>
                                Limpiar
                            </button>
                        </div>
                    </form>

                    {(error || result) && (
                        <section className={`result result--${resultTone}`}>
                            <h3 className="result__headline">{getResultHeadline(result, error)}</h3>
                            <p className="result__copy">{getResultCopy(result, error)}</p>

                            {result && (
                                <div className="result__grid">
                                    <div className="result__metric">
                                        <span>CUIL</span>
                                        <strong>{result.cuil || 'Sin dato'}</strong>
                                    </div>
                                    <div className="result__metric">
                                        <span>Saldo renovacion</span>
                                        <strong>{typeof result.saldo_renovacion === 'number' ? currencyFormatter.format(result.saldo_renovacion) : 'No informado'}</strong>
                                    </div>
                                    <div className="result__metric">
                                        <span>Puede renovar</span>
                                        <strong>{result.puede_renovar ? 'Si' : 'No'}</strong>
                                    </div>
                                    <div className="result__metric">
                                        <span>Motivo</span>
                                        <strong>{humanizeReason(result.motivo || result.error || 'Sin detalle')}</strong>
                                    </div>
                                </div>
                            )}
                        </section>
                    )}
                </aside>
            </div>

            <section className="panel section">
                <p className="section__eyebrow">Escalable sin complejidad</p>
                <h2 className="section__title">Un mismo lenguaje visual para todas las herramientas.</h2>
                <p className="section__copy">La pagina esta preparada para crecer como un catalogo interno de accesos. Cada nueva herramienta puede sumarse manualmente manteniendo la misma identidad institucional, sin forzar una base de datos ni un panel de administracion desde el dia uno.</p>
                <div className="footer-note">
                    <span>{branding.support_copy}</span>
                    <a href={branding.support_url} target="_blank" rel="noreferrer">Coordinar siguiente alta</a>
                </div>
            </section>
        </div>
    );
}

function getResultTone(result, error) {
    if (error || (result && result.ok === false)) {
        return 'error';
    }

    if (result && result.puede_renovar) {
        return 'success';
    }

    return 'warning';
}

function getResultHeadline(result, error) {
    if (error) {
        return 'No se pudo completar la consulta';
    }

    if (!result) {
        return '';
    }

    if (result.ok && result.puede_renovar) {
        return 'El socio puede renovar';
    }

    if (result.ok) {
        return 'El socio no puede renovar por ahora';
    }

    return 'La consulta devolvio una validacion';
}

function getResultCopy(result, error) {
    if (error) {
        return error;
    }

    if (!result) {
        return '';
    }

    if (result.ok && result.puede_renovar) {
        return 'La herramienta recibio una respuesta positiva desde Kestra y devolvio el saldo de renovacion disponible.';
    }

    if (result.ok) {
        return `Motivo informado por el flujo: ${humanizeReason(result.motivo || 'sin detalle')}.`;
    }

    return result.message || result.error || 'La consulta devolvio una respuesta no esperada.';
}

function humanizeReason(value) {
    return String(value)
        .replaceAll('_', ' ')
        .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

if (rootElement) {
    createRoot(rootElement).render(<App branding={initialPayload.branding || {}} tools={initialPayload.tools || []} />);
}