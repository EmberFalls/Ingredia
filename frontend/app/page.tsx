'use client';

import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  AlertTriangle,
  ArrowRight,
  Camera,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  History,
  Layers3,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  UserRound,
  X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  NativeSelect,
  NativeSelectOption,
} from '@/components/ui/native-select';
import {
  describeOcrQuality,
  extractIngredientSection,
  OCR_LANGUAGES,
  prepareOcrImage,
} from '@/lib/ocr';

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1';
const catalogImageUrl = (productId: string) =>
  `${API_BASE}/products/${encodeURIComponent(productId)}/image`;
function accountHeaders(json = false): Record<string, string> {
  const headers: Record<string, string> = json
    ? { 'Content-Type': 'application/json' }
    : {};
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('ingredientiq_session');
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

type Evidence = {
  concern_type: string;
  confidence: number;
  source_name: string;
  source_url: string | null;
  summary: string;
  applicability: string;
  limitations: string | null;
};
type Ingredient = {
  position: number;
  raw_token: string;
  canonical_name: string | null;
  match: { method: string; confidence: number } | null;
  concern_score: number;
  evidence: Evidence[];
  personal_alert: { preference_type: string; message: string } | null;
};
type Analysis = {
  analysis_id: string;
  summary: {
    concern_score: number;
    score_band: string;
    coverage: number;
    parsed_ingredients: number;
    unknown_ingredients: number;
    personal_alerts: number;
    high_confidence_flags: number;
  };
  ingredients: Ingredient[];
  unknowns: string[];
  score_breakdown: {
    top_contributors: { ingredient: string; contribution: number }[];
    scoring_version: string;
  };
  disclaimer: string;
};
type Comparison = {
  product_a: Analysis;
  product_b: Analysis;
  shared_ingredients: string[];
  only_in_a: string[];
  only_in_b: string[];
};
type CatalogProduct = {
  id: string;
  name: string;
  brand: string;
  category: string | null;
  barcode: string | null;
  ingredient_text: string;
  image_url: string | null;
  description: string | null;
  source_type: string;
  source_name: string;
  source_url: string | null;
  source_confidence: number;
  label_verified_at: string | null;
  source_retrieved_at: string | null;
  is_demo: boolean;
  ingredients_available: boolean;
};
type ProfileSetup = {
  ingredients: string[];
  dietaryPreferences: string[];
  culturalConsiderations: string[];
};
type UserProfile = {
  user_id: string;
  display_name: string | null;
  avatar_url: string | null;
  dietary_preferences: string[];
  cultural_considerations: string[];
  additional_requirements: string | null;
};
type Preference = {
  ingredient_id: string;
  canonical_name: string;
  preference_type: string;
};
type Account = {
  id: string;
  email: string;
  display_name: string | null;
};
type AuthResponse = {
  access_token: string;
  token_type: string;
  account: Account;
};
type HistoryItem = {
  id: string;
  product_id: string | null;
  product_name: string | null;
  product_brand: string | null;
  product_category: string | null;
  product_image_url: string | null;
  product_source_name: string | null;
  product_source_type: string | null;
  raw_text: string;
  concern_score: number;
  coverage: number;
  created_at: string | null;
};
type View = 'analyze' | 'compare' | 'history' | 'catalog' | 'profile';
type WebModelContext = {
  registerTool: (
    tool: {
      name: string;
      title: string;
      description: string;
      inputSchema: object;
      execute: (input: unknown) => Promise<object>;
      annotations: { readOnlyHint: boolean; untrustedContentHint: boolean };
    },
    options: { signal: AbortSignal },
  ) => void | Promise<void>;
};

const confidence = (value: number) =>
  value >= 0.8
    ? 'High confidence'
    : value >= 0.6
      ? 'Medium confidence'
      : 'Limited evidence';
const scoreLabel = (band: string) =>
  band === 'elevated'
    ? 'Elevated concern'
    : band === 'moderate'
      ? 'Moderate concern'
      : 'Lower concern';
const tone = (score: number) =>
  score === 0 ? 'calm' : score < 20 ? 'watch' : 'review';

export default function Home() {
  const [stage, setStage] = useState<
    'landing' | 'login' | 'signup' | 'onboarding' | 'app'
  >('landing');
  const [name, setName] = useState('');
  const [view, setView] = useState<View>('analyze');
  const [draft, setDraft] = useState('');
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [catalogProduct, setCatalogProduct] = useState<CatalogProduct | null>(
    null,
  );
  const [recent, setRecent] = useState<Analysis[]>([]);
  const [selected, setSelected] = useState<Ingredient | null>(null);
  const [preferences, setPreferences] = useState<Preference[]>([]);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const userId = account?.id ?? 'local-demo';

  async function authenticate(
    mode: 'login' | 'signup',
    values: { email: string; password: string; displayName: string },
  ): Promise<string | null> {
    try {
      const response = await fetch(
        `${API_BASE}/auth/${mode === 'signup' ? 'register' : 'login'}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(
            mode === 'signup'
              ? {
                  email: values.email,
                  password: values.password,
                  display_name: values.displayName,
                }
              : { email: values.email, password: values.password },
          ),
        },
      );
      const payload = (await response.json()) as AuthResponse & {
        detail?: string;
      };
      if (!response.ok)
        return payload.detail ?? 'We could not access that account.';
      localStorage.setItem('ingredientiq_session', payload.access_token);
      setAccessToken(payload.access_token);
      setAccount(payload.account);
      setName(payload.account.display_name ?? payload.account.email.split('@')[0]);
      setStage(mode === 'signup' ? 'onboarding' : 'app');
      return null;
    } catch {
      return 'The account service is unavailable. Your details were not submitted.';
    }
  }

  async function logout() {
    if (accessToken)
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      }).catch(() => undefined);
    localStorage.removeItem('ingredientiq_session');
    setAccessToken(null);
    setAccount(null);
    setProfile(null);
    setPreferences([]);
    setAnalysis(null);
    setRecent([]);
    setName('');
    setStage('landing');
    setView('analyze');
  }

  async function requestAnalysis(text: string, save = true) {
    const response = await fetch(`${API_BASE}/analyses/text`, {
      method: 'POST',
      headers: accountHeaders(true),
      body: JSON.stringify({
        ingredient_text: text,
        product_name: 'Untitled product analysis',
        product_category: 'personal_care',
        user_id: userId,
        save_to_history: save,
      }),
    });
    if (!response.ok)
      throw new Error(
        'The analysis service could not process this ingredient list.',
      );
    return response.json() as Promise<Analysis>;
  }
  async function analyze(text = draft) {
    setLoading(true);
    setError(null);
    setView('analyze');
    try {
      const result = await requestAnalysis(text);
      setDraft(text);
      setCatalogProduct(null);
      setAnalysis(result);
      setRecent((items) =>
        [
          result,
          ...items.filter((item) => item.analysis_id !== result.analysis_id),
        ].slice(0, 4),
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Something interrupted the analysis. Your input is preserved.',
      );
    } finally {
      setLoading(false);
    }
  }
  async function analyzeCatalogProduct(product: CatalogProduct) {
    setLoading(true);
    setError(null);
    setView('analyze');
    try {
      const response = await fetch(
        `${API_BASE}/products/${product.id}/analyze`,
        {
          method: 'POST',
          headers: accountHeaders(true),
          body: JSON.stringify({
            user_id: userId,
            save_to_history: true,
          }),
        },
      );
      if (!response.ok)
        throw new Error(
          'The analysis service could not process this catalog product.',
        );
      const result = (await response.json()) as Analysis;
      setDraft(product.ingredient_text);
      setCatalogProduct(product);
      setAnalysis(result);
      setRecent((items) =>
        [
          result,
          ...items.filter((item) => item.analysis_id !== result.analysis_id),
        ].slice(0, 4),
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Something interrupted the analysis.',
      );
    } finally {
      setLoading(false);
    }
  }
  async function savePreference(ingredient: string) {
    try {
      const response = await fetch(`${API_BASE}/users/${userId}/preferences`, {
        method: 'PUT',
        headers: accountHeaders(true),
        body: JSON.stringify({
          ingredient_query: ingredient,
          preference_type: 'sensitivity',
        }),
      });
      if (!response.ok) throw new Error();
      const saved = (await response.json()) as Preference;
      setPreferences((items) =>
        items.some((item) => item.ingredient_id === saved.ingredient_id)
          ? items.map((item) =>
              item.ingredient_id === saved.ingredient_id ? saved : item,
            )
          : [...items, saved],
      );
      setError(null);
      if (analysis) await analyze(draft);
    } catch {
      setError('We could not save that preference. Please try again.');
    }
  }
  async function deletePreference(ingredientId: string) {
    const response = await fetch(
      `${API_BASE}/users/${userId}/preferences/${ingredientId}`,
      { method: 'DELETE', headers: accountHeaders() },
    );
    if (!response.ok) throw new Error('We could not remove that preference.');
    setPreferences((items) =>
      items.filter((item) => item.ingredient_id !== ingredientId),
    );
    setError(null);
  }
  async function saveProfile(next: UserProfile) {
    const response = await fetch(`${API_BASE}/users/${userId}/profile`, {
      method: 'PUT',
      headers: accountHeaders(true),
      body: JSON.stringify({
        display_name: next.display_name,
        avatar_url: next.avatar_url,
        dietary_preferences: next.dietary_preferences,
        cultural_considerations: next.cultural_considerations,
        additional_requirements: next.additional_requirements,
      }),
    });
    if (!response.ok) throw new Error('We could not save your profile.');
    const saved = (await response.json()) as UserProfile;
    setProfile(saved);
    setName(saved.display_name ?? name);
    return saved;
  }
  async function openHistory(item: HistoryItem) {
    setLoading(true);
    setError(null);
    setView('analyze');
    try {
      const productResponse = item.product_id
        ? await fetch(`${API_BASE}/products/${item.product_id}`)
        : null;
      const fetched = productResponse?.ok
        ? ((await productResponse.json()) as CatalogProduct)
        : null;
      const product =
        fetched ??
        (item.product_name
          ? {
              id: item.product_id ?? item.id,
              name: item.product_name,
              brand:
                item.product_brand ??
                item.product_source_name ??
                'Unknown brand',
              category: item.product_category,
              barcode: null,
              ingredient_text: item.raw_text,
              image_url: item.product_image_url,
              description: null,
              source_type: item.product_source_type ?? 'saved_analysis',
              source_name: item.product_source_name ?? 'Saved analysis',
              source_url: null,
              source_confidence: 0,
              label_verified_at: null,
              source_retrieved_at: item.created_at,
              is_demo: false,
              ingredients_available: true,
            }
          : null);
      const result = await requestAnalysis(item.raw_text, false);
      setDraft(item.raw_text);
      setCatalogProduct(product);
      setAnalysis(result);
    } catch {
      setError('We could not reopen that analysis.');
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    const savedToken = localStorage.getItem('ingredientiq_session');
    if (!savedToken) return;
    void fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${savedToken}` },
    })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const savedAccount = (await response.json()) as Account;
        setAccessToken(savedToken);
        setAccount(savedAccount);
        setName(
          savedAccount.display_name ?? savedAccount.email.split('@')[0],
        );
        setStage('app');
      })
      .catch(() => localStorage.removeItem('ingredientiq_session'));
  }, []);
  useEffect(() => {
    if (!account) return;
    void Promise.all([
      fetch(`${API_BASE}/users/${account.id}/profile`, {
        headers: accountHeaders(),
      }),
      fetch(`${API_BASE}/users/${account.id}/preferences`, {
        headers: accountHeaders(),
      }),
    ])
      .then(async ([profileResponse, preferenceResponse]) => {
        if (profileResponse.ok) {
          const saved = (await profileResponse.json()) as UserProfile;
          setProfile(saved);
        }
        if (preferenceResponse.ok) {
          const saved = (await preferenceResponse.json()) as Preference[];
          setPreferences(saved);
        }
      })
      .catch(() => undefined);
  }, [account]);
  useEffect(() => {
    const context = (document as Document & { modelContext?: WebModelContext })
      .modelContext;
    if (!context?.registerTool) return;
    const controller = new AbortController();
    void Promise.resolve(
      context.registerTool(
        {
          name: 'analyze_ingredient_list',
          title: 'Analyze ingredient list',
          description:
            'Analyze a pasted ingredient list and update the visible ingredient workspace.',
          inputSchema: {
            type: 'object',
            properties: { ingredientText: { type: 'string', minLength: 1 } },
            required: ['ingredientText'],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: true },
          async execute(input) {
            const text =
              input && typeof input === 'object'
                ? (input as { ingredientText?: unknown }).ingredientText
                : undefined;
            if (typeof text !== 'string' || !text.trim())
              throw new Error('ingredientText must be a non-empty string.');
            const result = await requestAnalysis(text);
            setDraft(text);
            setAnalysis(result);
            setRecent((items) => [result, ...items].slice(0, 4));
            setStage('app');
            setView('analyze');
            return {
              concernScore: result.summary.concern_score,
              coverage: result.summary.coverage,
              unknownIngredients: result.summary.unknown_ingredients,
            };
          },
        },
        { signal: controller.signal },
      ),
    ).catch(() => undefined);
    return () => controller.abort();
  }, [userId]);

  if (stage === 'landing')
    return (
      <Landing
        onLogin={() => setStage('login')}
        onSignup={() => setStage('signup')}
      />
    );
  if (stage === 'login')
    return (
      <AuthPage
        mode="login"
        onBack={() => setStage('landing')}
        onSwitch={() => setStage('signup')}
        onContinue={(values) => authenticate('login', values)}
      />
    );
  if (stage === 'signup')
    return (
      <AuthPage
        mode="signup"
        onBack={() => setStage('landing')}
        onSwitch={() => setStage('login')}
        onContinue={(values) => authenticate('signup', values)}
      />
    );
  if (stage === 'onboarding')
    return (
      <Onboarding
        name={name}
        onSkip={() => setStage('app')}
        onComplete={async (profile) => {
          for (const ingredient of profile.ingredients)
            await savePreference(ingredient);
          const response = await fetch(`${API_BASE}/users/${userId}/profile`, {
            method: 'PUT',
            headers: accountHeaders(true),
            body: JSON.stringify({
              display_name: name || null,
              dietary_preferences: profile.dietaryPreferences,
              cultural_considerations: profile.culturalConsiderations,
            }),
          });
          if (!response.ok)
            setError('Your safety profile could not be saved completely.');
          else setError(null);
          setStage('app');
        }}
      />
    );
  return (
    <AppShell
      name={name}
      view={view}
      setView={setView}
      draft={draft}
      setDraft={setDraft}
      analysis={analysis}
      catalogProduct={catalogProduct}
      recent={recent}
      selected={selected}
      setSelected={setSelected}
      preferences={preferences}
      profile={profile}
      loading={loading}
      error={error}
      userId={userId}
      onAnalyze={analyze}
      onAnalyzeProduct={analyzeCatalogProduct}
      onSavePreference={savePreference}
      onDeletePreference={deletePreference}
      onSaveProfile={saveProfile}
      onOpenHistory={openHistory}
      onLogout={logout}
    />
  );
}

function Brand() {
  return (
    <span className="brand">
      <span className="brand-wordmark">
        ingredient<span>IQ</span>
      </span>
    </span>
  );
}

function Landing({
  onLogin,
  onSignup,
}: {
  onLogin: () => void;
  onSignup: () => void;
}) {
  return (
    <main className="auth-page landing-page">
      <section className="landing-hero">
        <div className="landing-nav">
          <Brand />
          <div>
            <button className="nav-text-button" onClick={onLogin}>
              Log in
            </button>
            <Button className="nav-cta" onClick={onSignup}>
              Get started <ArrowRight />
            </Button>
          </div>
        </div>
        <div className="landing-copy">
          <p className="live-pill">
            <i /> Ingredient intelligence for everyday labels
          </p>
          <h1>
            Know what’s in your food.
            <br />
            <span>Choose with clarity.</span>
          </h1>
          <p>
            Paste an ingredient list, scan a package, or search a product.
            IngredientIQ recognizes label terms, connects them to source
            records, and highlights what matters to your own food context.
          </p>
          <div className="landing-actions">
            <Button className="landing-primary" onClick={onSignup}>
              Analyze a label <ArrowRight />
            </Button>
            <button
              className="landing-secondary"
              onClick={() =>
                document
                  .getElementById('product-story')
                  ?.scrollIntoView({ behavior: 'smooth' })
              }
            >
              Explore the product <ChevronDown size={16} />
            </button>
          </div>
          <div className="landing-proof">
            <span>
              <b>100</b> catalog products
            </span>
            <span>
              <b>19</b> normalized ingredient records
            </span>
            <span>
              <b>9</b> major allergen groups
            </span>
          </div>
        </div>
        <div
          className="landing-stage"
          aria-label="Animated ingredient analysis example"
        >
          <div className="stage-grid" />
          <div className="stage-glow" />
          <div className="label-card">
            <div className="label-card__head">
              <span>Oat milk</span>
              <i>new label</i>
            </div>
            <b>Ingredients</b>
            <p>Oats · Water · Sea salt · Gellan gum</p>
            <div className="label-card__scan">
              <span />
            </div>
          </div>
          <div className="analysis-card">
            <div className="analysis-card__top">
              <span>IngredientIQ analysis</span>
              <i>
                <Sparkles size={13} /> Live
              </i>
            </div>
            <div className="analysis-line">
              <span className="signal signal--calm" />
              <b>Oats</b>
              <small>recognized</small>
              <Check size={15} />
            </div>
            <div className="analysis-line">
              <span className="signal signal--calm" />
              <b>Sea salt</b>
              <small>recognized</small>
              <Check size={15} />
            </div>
            <div className="analysis-line analysis-line--pending">
              <span className="signal" />
              <b>Gellan gum</b>
              <small>reviewing evidence</small>
              <LoaderCircle size={15} />
            </div>
            <div className="analysis-score">
              <span>Label coverage</span>
              <strong>100%</strong>
            </div>
          </div>
          <div className="floating-tag tag-one">
            <Check size={14} /> Personal context ready
          </div>
          <div className="floating-tag tag-two">
            <ShieldCheck size={14} /> Evidence matched
          </div>
        </div>
      </section>
      <section className="product-story" id="product-story">
        <div className="product-story__intro">
          <p className="eyebrow">What IngredientIQ actually does</p>
          <h2>From package text to a decision you can understand.</h2>
          <p>
            IngredientIQ does not guess from a product name. It reads the
            ingredient information you provide or retrieve from the catalog,
            resolves familiar and alternate ingredient terms, then layers
            source-backed evidence and your selected needs on top.
          </p>
        </div>
        <div
          className="product-flow"
          aria-label="IngredientIQ analysis pipeline"
        >
          <article>
            <span className="flow-number">01</span>
            <div className="flow-icon">
              <Camera size={20} />
            </div>
            <h3>Bring in a label</h3>
            <p>
              Paste ingredients, upload a label photo for local OCR, scan a
              barcode, or search by product and company.
            </p>
            <i className="flow-connector" />
          </article>
          <article>
            <span className="flow-number">02</span>
            <div className="flow-icon">
              <Layers3 size={20} />
            </div>
            <h3>Resolve the ingredients</h3>
            <p>
              We match label aliases such as “E211,” “Aqua,” or “whey” to known
              ingredient records where possible.
            </p>
            <i className="flow-connector" />
          </article>
          <article>
            <span className="flow-number">03</span>
            <div className="flow-icon">
              <ShieldCheck size={20} />
            </div>
            <h3>Explain the result</h3>
            <p>
              You get label coverage, cited evidence context, and separate
              alerts for allergens, sensitivities, diet, and values.
            </p>
          </article>
        </div>
        <div className="catalog-strip">
          <div>
            <p className="eyebrow">Current local catalog</p>
            <h3>Built to grow beyond a static ingredient checker.</h3>
            <p>
              The local catalog contains 100 searchable packaged-food products.
              Every record includes its official package image, UPC, ingredient
              label, and first-party product-page provenance.
            </p>
            <Button variant="outline" onClick={onSignup}>
              Search the catalog <ArrowRight />
            </Button>
          </div>
          <div className="catalog-cards" aria-hidden="true">
            <div className="catalog-mini-card">
              <span>Product search</span>
              <b>Company + product</b>
              <small>Catalog lookup ready</small>
            </div>
            <div className="catalog-mini-card catalog-mini-card--active">
              <span>Evidence layer</span>
              <b>Source-aware</b>
              <small>Context, not a diagnosis</small>
            </div>
            <div className="catalog-mini-card">
              <span>Safety context</span>
              <b>Kept personal</b>
              <small>Separate from score</small>
            </div>
          </div>
        </div>
      </section>
      <section className="landing-final">
        <div>
          <p className="eyebrow">A better way to read labels</p>
          <h2>Ready to see a label clearly?</h2>
          <p>
            Start with the ingredients already in front of you. Your profile
            helps keep the answer relevant without turning it into medical
            advice.
          </p>
        </div>
        <Button className="landing-primary" onClick={onSignup}>
          Start analyzing <ArrowRight />
        </Button>
      </section>
    </main>
  );
}
function AuthPage({
  mode,
  onBack,
  onSwitch,
  onContinue,
}: {
  mode: 'login' | 'signup';
  onBack: () => void;
  onSwitch: () => void;
  onContinue: (values: {
    email: string;
    password: string;
    displayName: string;
  }) => Promise<string | null>;
}) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const isSignup = mode === 'signup';
  const submit = async () => {
    setSubmitting(true);
    setFormError(null);
    const nextError = await onContinue({ email, password, displayName });
    setFormError(nextError);
    setSubmitting(false);
  };
  return (
    <main className="account-page">
      <div className="account-ambient account-ambient--one" />
      <div className="account-ambient account-ambient--two" />
      <header className="account-nav">
        <button onClick={onBack}>
          <Brand />
        </button>
        <button className="account-back" onClick={onBack}>
          ← Back to home
        </button>
      </header>
      <section className="account-layout">
        <div className="account-intro">
          <p className="live-pill">
            <i /> A calmer way to read labels
          </p>
          <h1>
            {isSignup ? (
              <>
                Make every label
                <br />
                <span>more personal.</span>
              </>
            ) : (
              <>
                Welcome back to
                <br />
                <span>your label guide.</span>
              </>
            )}
          </h1>
          <p>
            {isSignup
              ? 'Create your IngredientIQ account, then build the personal context that makes label analysis more relevant to you.'
              : 'Pick up where you left off—your saved analyses, catalog checks, and food context are ready.'}
          </p>
        </div>
        <section className="auth-access-card">
          <div className="account-card__top">
            <p className="eyebrow">{isSignup ? 'Create account' : 'Sign in'}</p>
            <h2>
              {isSignup
                ? 'Start your IngredientIQ profile.'
                : 'Good to see you again.'}
            </h2>
            <p>
              {isSignup ? 'Already have an account?' : 'New to IngredientIQ?'}{' '}
              <button onClick={onSwitch}>
                {isSignup ? 'Log in' : 'Create an account'}
              </button>
            </p>
          </div>
          <form
            className="account-form"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            {isSignup && (
              <label htmlFor="signup-name">
                Your name
                <Input
                  id="signup-name"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  autoComplete="name"
                  required
                />
              </label>
            )}
            <label htmlFor="account-email">
              Email address
              <Input
                id="account-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </label>
            <label htmlFor="account-password">
              Password
              <Input
                id="account-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete={isSignup ? 'new-password' : 'current-password'}
                minLength={8}
                required
              />
            </label>
            {isSignup && (
              <label className="terms-row">
                <input type="checkbox" required />{' '}
                <span>
                  I agree to the terms and understand IngredientIQ is not
                  medical advice.
                </span>
              </label>
            )}
            <Button
              type="submit"
              className="primary-action account-submit"
              disabled={submitting}
            >
              {submitting ? (
                <LoaderCircle className="animate-spin" />
              ) : isSignup ? (
                'Create account'
              ) : (
                'Log in'
              )}{' '}
              {!submitting && <ArrowRight />}
            </Button>
          </form>
          {formError && (
            <p className="account-form-error" role="alert">
              <AlertTriangle size={15} /> {formError}
            </p>
          )}
          <p className="account-foot">
            <LockKeyhole size={13} /> Your password is salted and hashed before
            it is stored locally.
          </p>
        </section>
      </section>
    </main>
  );
}
function Onboarding({
  name,
  onSkip,
  onComplete,
}: {
  name: string;
  onSkip: () => void;
  onComplete: (profile: ProfileSetup) => Promise<void>;
}) {
  const [step, setStep] = useState(1),
    [focus, setFocus] = useState<string[]>(['Allergens']),
    [items, setItems] = useState<string[]>([]),
    [input, setInput] = useState(''),
    [saving, setSaving] = useState(false),
    [diet, setDiet] = useState<string[]>([]),
    [beliefs, setBeliefs] = useState<string[]>([]);
  function addItem() {
    const value = input.trim();
    if (value && !items.includes(value)) setItems([...items, value]);
    setInput('');
  }
  const toggle = (
    value: string,
    setValues: (values: string[]) => void,
    values: string[],
  ) =>
    setValues(
      values.includes(value)
        ? values.filter((item) => item !== value)
        : [...values, value],
    );
  const stepTitle = [
    'Your safety context',
    'Ingredients to recognize',
    'Food choices that matter',
    'Your profile is ready',
  ][step - 1];
  const stepReason = [
    {
      title: 'Why this matters',
      copy: 'Allergens, intolerances, and ingredients you avoid are surfaced as personal alerts when a label is analyzed.',
    },
    {
      title: 'What we do with it',
      copy: 'We look for the terms you add and known aliases, so “whey” can still be relevant when you add “milk.”',
    },
    {
      title: 'How it helps',
      copy: 'Dietary and cultural choices help you evaluate a label on your terms, separate from scientific evidence records.',
    },
    {
      title: 'What stays separate',
      copy: 'Your personal selections make results more useful; they do not alter the general ingredient score.',
    },
  ][step - 1];
  return (
    <main className="onboarding-page">
      <div className="onboarding-shell">
        <aside className="onboarding-aside">
          <div className="onboarding-brand">
            <Brand />
            <span>Set up your guide</span>
          </div>
          <div className="onboarding-orb">
            <div className="onboarding-orb__core">
              <span>{String(step).padStart(2, '0')}</span>
              <b>{stepReason.title}</b>
            </div>
            <i />
            <i />
            <i />
          </div>
          <div className="onboarding-aside-copy" key={step}>
            <p className="eyebrow">{stepTitle}</p>
            <h2>{stepReason.title}</h2>
            <p>{stepReason.copy}</p>
          </div>
          <div className="onboarding-mini-summary">
            <span>
              <i className={focus.length ? 'filled' : ''} /> Safety areas{' '}
              <b>{focus.length}</b>
            </span>
            <span>
              <i className={items.length ? 'filled' : ''} /> Ingredients{' '}
              <b>{items.length}</b>
            </span>
            <span>
              <i className={diet.length + beliefs.length ? 'filled' : ''} />{' '}
              Food choices <b>{diet.length + beliefs.length}</b>
            </span>
          </div>
        </aside>
        <section className="onboarding-card">
          <header className="onboarding-top">
            <div>
              <span className="onboarding-kicker">Profile setup</span>
              <b>Step {step} of 4</b>
            </div>
            <button onClick={onSkip}>Skip for now</button>
          </header>
          <div className="onboarding-progress" aria-label={`Step ${step} of 4`}>
            <span style={{ width: `${(step / 4) * 100}%` }} />
          </div>
          <div className="onboarding-step-label">
            <span>{String(step).padStart(2, '0')}</span>
            <p>{stepTitle}</p>
          </div>
          <div className="onboarding-screen" key={step}>
            {step === 1 && (
              <>
                <h1>
                  What should we
                  <br />
                  <span>keep in view?</span>
                </h1>
                <p className="lead">
                  Pick every area that may matter to you. Personal matches stay
                  separate from the general evidence score.
                </p>
                <div className="choice-grid choice-grid--rich">
                  {[
                    'Allergens',
                    'Intolerances & irritations',
                    'Ingredients I prefer to avoid',
                  ].map((option, index) => (
                    <button
                      key={option}
                      onClick={() => toggle(option, setFocus, focus)}
                      className={`choice ${focus.includes(option) ? 'choice--selected' : ''}`}
                    >
                      <span>
                        {focus.includes(option) ? (
                          <Check size={14} />
                        ) : (
                          String(index + 1).padStart(2, '0')
                        )}
                      </span>
                      <div>
                        <b>{option}</b>
                        <small>
                          {option === 'Allergens'
                            ? 'Highlight ingredients you need to avoid.'
                            : option === 'Intolerances & irritations'
                              ? 'Keep non-allergic reactions visible.'
                              : 'Apply your personal ingredient preferences.'}
                        </small>
                      </div>
                      <ChevronRight size={16} />
                    </button>
                  ))}
                </div>
                <div className="onboarding-actions">
                  <Button variant="ghost" onClick={onSkip}>
                    I’ll set this up later
                  </Button>
                  <Button className="primary-action" onClick={() => setStep(2)}>
                    Continue <ArrowRight />
                  </Button>
                </div>
              </>
            )}
            {step === 2 && (
              <>
                <h1>
                  Add the names
                  <br />
                  <span>you recognize.</span>
                </h1>
                <p className="lead">
                  Add allergens, sensitivities, ingredients you avoid, or terms
                  you want surfaced. We’ll match known aliases where possible.
                </p>
                <div className="onboarding-input-wrap">
                  <div className="profile-input">
                    <Search size={17} />
                    <Input
                      placeholder="e.g. milk, peanuts, gluten"
                      value={input}
                      onChange={(event) => setInput(event.target.value)}
                      onKeyDown={(event) =>
                        event.key === 'Enter' &&
                        (event.preventDefault(), addItem())
                      }
                    />
                    <Button size="sm" type="button" onClick={addItem}>
                      Add
                    </Button>
                  </div>
                  <p>
                    <Sparkles size={14} /> You can change these from your
                    profile at any time.
                  </p>
                </div>
                <div className="chip-list onboarding-chips">
                  {items.length ? (
                    items.map((item) => (
                      <button
                        key={item}
                        className="chip"
                        onClick={() =>
                          setItems(items.filter((value) => value !== item))
                        }
                      >
                        {item} <X size={13} />
                      </button>
                    ))
                  ) : (
                    <span className="empty-chip-copy">
                      Nothing added yet — that’s okay.
                    </span>
                  )}
                </div>
                <div className="onboarding-actions">
                  <Button variant="ghost" onClick={() => setStep(1)}>
                    Back
                  </Button>
                  <Button className="primary-action" onClick={() => setStep(3)}>
                    Continue <ArrowRight />
                  </Button>
                </div>
              </>
            )}
            {step === 3 && (
              <>
                <h1>
                  Make the result
                  <br />
                  <span>feel like yours.</span>
                </h1>
                <p className="lead">
                  Choose dietary patterns and cultural or religious
                  considerations you want visible during label analysis.
                </p>
                <div className="preference-groups onboarding-preferences">
                  <div>
                    <b>Dietary pattern</b>
                    <small>Useful for organizing your label checks</small>
                    <div>
                      {[
                        'Vegetarian',
                        'Vegan',
                        'Gluten-free',
                        'Dairy-free',
                        'Low sodium',
                      ].map((option) => (
                        <button
                          key={option}
                          onClick={() => toggle(option, setDiet, diet)}
                          className={diet.includes(option) ? 'selected' : ''}
                        >
                          {diet.includes(option) && <Check size={13} />}
                          {option}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <b>Cultural or religious considerations</b>
                    <small>Kept as separate personal context</small>
                    <div>
                      {[
                        'Halal',
                        'Kosher',
                        'Jain',
                        'Hindu vegetarian',
                        'No alcohol',
                      ].map((option) => (
                        <button
                          key={option}
                          onClick={() => toggle(option, setBeliefs, beliefs)}
                          className={beliefs.includes(option) ? 'selected' : ''}
                        >
                          {beliefs.includes(option) && <Check size={13} />}
                          {option}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="onboarding-actions">
                  <Button variant="ghost" onClick={() => setStep(2)}>
                    Back
                  </Button>
                  <Button className="primary-action" onClick={() => setStep(4)}>
                    Review profile <ArrowRight />
                  </Button>
                </div>
              </>
            )}
            {step === 4 && (
              <>
                <div className="ready-icon">
                  <Check size={30} />
                </div>
                <h1>
                  Your guide is
                  <br />
                  <span>ready for labels.</span>
                </h1>
                <p className="lead">
                  {name ? `${name}, IngredientIQ` : 'IngredientIQ'} will use this context to surface relevance
                  without changing the general, evidence-backed assessment.
                </p>
                <div className="profile-summary onboarding-summary">
                  <span>
                    <b>{focus.length}</b> safety areas
                  </span>
                  <span>
                    <b>{items.length}</b> highlighted ingredients
                  </span>
                  <span>
                    <b>{diet.length + beliefs.length}</b> food choices
                  </span>
                </div>
                <div className="onboarding-actions">
                  <Button variant="ghost" onClick={() => setStep(3)}>
                    Back
                  </Button>
                  <Button
                    className="primary-action"
                    disabled={saving}
                    onClick={async () => {
                      setSaving(true);
                      await onComplete({
                        ingredients: items,
                        dietaryPreferences: diet,
                        culturalConsiderations: beliefs,
                      });
                    }}
                  >
                    {saving ? (
                      <LoaderCircle className="animate-spin" />
                    ) : (
                      'Open workspace'
                    )}{' '}
                    {!saving && <ArrowRight />}
                  </Button>
                </div>
              </>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function AppShell({
  name,
  view,
  setView,
  draft,
  setDraft,
  analysis,
  catalogProduct,
  recent,
  selected,
  setSelected,
  preferences,
  profile,
  loading,
  error,
  onAnalyze,
  onAnalyzeProduct,
  onSavePreference,
  onDeletePreference,
  onSaveProfile,
  onOpenHistory,
  onLogout,
  userId,
}: {
  name: string;
  view: View;
  setView: (view: View) => void;
  draft: string;
  setDraft: (value: string) => void;
  analysis: Analysis | null;
  catalogProduct: CatalogProduct | null;
  recent: Analysis[];
  selected: Ingredient | null;
  setSelected: (ingredient: Ingredient | null) => void;
  preferences: Preference[];
  profile: UserProfile | null;
  loading: boolean;
  error: string | null;
  onAnalyze: (text?: string) => Promise<void>;
  onAnalyzeProduct: (product: CatalogProduct) => Promise<void>;
  onSavePreference: (ingredient: string) => Promise<void>;
  onDeletePreference: (ingredientId: string) => Promise<void>;
  onSaveProfile: (profile: UserProfile) => Promise<UserProfile>;
  onOpenHistory: (item: HistoryItem) => Promise<void>;
  onLogout: () => Promise<void>;
  userId: string;
}) {
  const profileMenu = useRef<HTMLDetailsElement>(null);
  const openAccountView = (nextView: 'profile' | 'history') => {
    profileMenu.current?.removeAttribute('open');
    setView(nextView);
  };
  return (
    <main className="app-page">
      <header className="app-nav">
        <div className="app-shell">
          <button onClick={() => setView('analyze')}>
            <Brand />
          </button>
          <nav>
            {(['analyze', 'compare', 'catalog'] as View[]).map((item) => (
              <button
                key={item}
                onClick={() => setView(item)}
                className={view === item ? 'selected' : ''}
              >
                {item}
              </button>
            ))}
          </nav>
          <details
            className="profile-menu-wrap"
            ref={profileMenu}
          >
            <summary className="profile-menu" aria-label="Open account menu">
              <span className="profile-avatar">
                {profile?.avatar_url ? (
                  <img src={profile.avatar_url} alt="" />
                ) : (
                  name.slice(0, 1).toUpperCase() || 'U'
                )}
              </span>
              <span className="hidden sm:inline">{name || 'Profile'}</span>
              <ChevronDown size={15} />
            </summary>
            <div className="profile-dropdown">
              <span className="profile-dropdown__label">Your account</span>
              <button onClick={() => openAccountView('profile')}>
                <UserRound /> Profile
              </button>
              <button onClick={() => openAccountView('history')}>
                <History /> History
              </button>
              <button onClick={() => void onLogout()}>
                <LogOut /> Log out
              </button>
            </div>
          </details>
        </div>
      </header>
      <div className="app-shell app-content">
        {view === 'analyze' && (
          <AnalyzePage
            name={name}
            draft={draft}
            setDraft={setDraft}
            analysis={analysis}
            catalogProduct={catalogProduct}
            recent={recent}
            loading={loading}
            error={error}
            onAnalyze={onAnalyze}
            onOpenCatalog={() => setView('catalog')}
            onSelect={setSelected}
          />
        )}
        {view === 'compare' && (
          <ComparePage onSelect={setSelected} userId={userId} />
        )}
        {view === 'history' && (
          <HistoryPage onOpen={onOpenHistory} userId={userId} />
        )}
        {view === 'catalog' && (
          <CatalogPage onAnalyzeProduct={onAnalyzeProduct} userId={userId} />
        )}
        {view === 'profile' && (
          <ProfilePage
            name={name}
            preferences={preferences}
            profile={profile}
            userId={userId}
            onSave={onSavePreference}
            onDelete={onDeletePreference}
            onSaveProfile={onSaveProfile}
          />
        )}
      </div>
      <IngredientDrawer
        ingredient={selected}
        onClose={() => setSelected(null)}
        onSave={onSavePreference}
      />
    </main>
  );
}

function AnalyzePage({
  name,
  draft,
  setDraft,
  analysis,
  catalogProduct,
  recent,
  loading,
  error,
  onAnalyze,
  onOpenCatalog,
  onSelect,
}: {
  name: string;
  draft: string;
  setDraft: (value: string) => void;
  analysis: Analysis | null;
  catalogProduct: CatalogProduct | null;
  recent: Analysis[];
  loading: boolean;
  error: string | null;
  onAnalyze: (text?: string) => Promise<void>;
  onOpenCatalog: () => void;
  onSelect: (ingredient: Ingredient) => void;
}) {
  const [mode, setMode] = useState<'ingredients' | 'product'>('ingredients');
  const [menuOpen, setMenuOpen] = useState(false);
  const [ocrMessage, setOcrMessage] = useState<string | null>(null);
  const [ocrError, setOcrError] = useState<string | null>(null);
  const [ocrLanguage, setOcrLanguage] = useState('eng');
  const [ocrRotation, setOcrRotation] = useState(0);
  const [ocrCrop, setOcrCrop] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  async function extractLabel(file: File) {
    if (!file.type.startsWith('image/')) {
      setOcrError('Choose an image file of the ingredient label.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setOcrError('Choose an image smaller than 10 MB.');
      return;
    }
    setMenuOpen(false);
    setOcrError(null);
    setOcrMessage('Preparing label scan…');
    try {
      const { recognize } = await import('tesseract.js');
      const prepared = await prepareOcrImage(file, ocrRotation, ocrCrop);
      const result = await recognize(prepared, ocrLanguage, {
        logger: (event) => {
          if (
            event.status === 'recognizing text' &&
            typeof event.progress === 'number'
          )
            setOcrMessage(
              `Reading label… ${Math.round(event.progress * 100)}%`,
            );
        },
      });
      const extracted = extractIngredientSection(result.data.text);
      if (!extracted.text) throw new Error('No text found');
      setDraft(extracted.text);
      setMode('ingredients');
      setOcrMessage(
        describeOcrQuality(result.data.confidence, extracted.sectionFound),
      );
    } catch {
      setOcrError(
        'We could not read that label. Try a sharper, well-lit photo or paste the ingredients instead.',
      );
      setOcrMessage(null);
    } finally {
      if (fileInput.current) fileInput.current.value = '';
    }
  }

  return (
    <>
      <section className="workspace-hero">
        <p className="eyebrow">
          {analysis
            ? `Welcome back, ${name || 'there'}`
            : 'Evidence-led product analysis'}
        </p>
        <h1>
          Understand the label.
          <br />
          <span>Not the marketing.</span>
        </h1>
        <p className="lead">
          We identify ingredients, resolve aliases, compare evidence, and show
          what is personally relevant — without turning a label into a
          diagnosis.
        </p>
      </section>
      <section className="composer-zone">
        <div className="composer-tabs">
          <button
            onClick={() => setMode('ingredients')}
            className={mode === 'ingredients' ? 'active' : ''}
          >
            Ingredients
          </button>
          <button
            onClick={() => setMode('product')}
            className={mode === 'product' ? 'active' : ''}
          >
            Product
          </button>
        </div>
        <div className="composer">
          <div className="plus-wrap">
            <button
              className="plus-button"
              onClick={() => setMenuOpen(!menuOpen)}
              aria-expanded={menuOpen}
              aria-label="Input options"
            >
              <Plus />
            </button>
            {menuOpen && (
              <div className="attachment-menu">
                <NativeSelect
                  size="sm"
                  value={ocrLanguage}
                  onChange={(event) => setOcrLanguage(event.target.value)}
                  aria-label="Label language"
                >
                  {OCR_LANGUAGES.map((language) => (
                    <NativeSelectOption
                      key={language.code}
                      value={language.code}
                    >
                      {language.label}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
                <NativeSelect
                  size="sm"
                  value={String(ocrRotation)}
                  onChange={(event) =>
                    setOcrRotation(Number(event.target.value))
                  }
                  aria-label="Image rotation"
                >
                  <NativeSelectOption value="0">No rotation</NativeSelectOption>
                  <NativeSelectOption value="90">
                    Rotate right
                  </NativeSelectOption>
                  <NativeSelectOption value="180">
                    Rotate 180°
                  </NativeSelectOption>
                  <NativeSelectOption value="270">
                    Rotate left
                  </NativeSelectOption>
                </NativeSelect>
                <label className="remember">
                  <input
                    type="checkbox"
                    checked={ocrCrop}
                    onChange={(event) => setOcrCrop(event.target.checked)}
                  />{' '}
                  Crop outer edges
                </label>
                <button onClick={() => fileInput.current?.click()}>
                  <Upload size={14} /> Scan label image
                </button>
              </div>
            )}
            <input
              ref={fileInput}
              type="file"
              accept="image/*"
              className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void extractLabel(file);
              }}
            />
          </div>
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            aria-label="Ingredient analysis input"
            disabled={mode === 'product'}
          />
          <Button
            className="send-button"
            onClick={() => (mode === 'product' ? onOpenCatalog() : onAnalyze())}
            disabled={
              loading ||
              !!ocrMessage?.includes('…') ||
              (mode === 'ingredients' && !draft.trim())
            }
          >
            {loading ? (
              <LoaderCircle className="animate-spin" />
            ) : (
              <ArrowRight />
            )}
          </Button>
        </div>
        <p className="composer-hint">
          <Sparkles size={14} />{' '}
          {mode === 'ingredients'
            ? 'Alias-aware ingredient matching'
            : 'Search the catalog by product name or company'}
        </p>
        {ocrMessage && (
          <p className="composer-hint" role="status">
            <Sparkles size={14} /> {ocrMessage}
          </p>
        )}
        {ocrError && (
          <div className="error-note" role="alert">
            <AlertTriangle size={18} /> {ocrError}
          </div>
        )}
      </section>
      {error && (
        <div className="error-note" role="alert">
          <AlertTriangle size={18} /> {error}
        </div>
      )}
      {loading && <AnalysisProgress />}
      {analysis && !loading && (
        <AnalysisResult
          analysis={analysis}
          product={catalogProduct}
          onSelect={onSelect}
        />
      )}
      {!analysis && !loading && <RecentPanel recent={recent} />}
    </>
  );
}

function AnalysisProgress() {
  return (
    <section className="analysis-progress" aria-live="polite">
      <div>
        <p className="eyebrow">Analyzing your product</p>
        <h2>Building an evidence-led picture.</h2>
      </div>
      <ol>
        {[
          'Ingredient list detected',
          'Aliases normalized',
          'Evidence checked',
          'Profile compared',
          'Structured result prepared',
        ].map((item, index) => (
          <li key={item} className={index < 2 ? 'done' : ''}>
            <span>
              {index < 2 ? (
                <Check size={14} />
              ) : (
                <LoaderCircle size={14} className="animate-spin" />
              )}
            </span>
            {item}
          </li>
        ))}
      </ol>
    </section>
  );
}

function AnalysisResult({
  analysis,
  product,
  onSelect,
}: {
  analysis: Analysis;
  product: CatalogProduct | null;
  onSelect: (ingredient: Ingredient) => void;
}) {
  const personal = analysis.ingredients.filter((item) => item.personal_alert);
  const coverage = Math.round(analysis.summary.coverage * 100);
  return (
    <section className="results-section">
      <div className="product-summary">
        <div>
          <p className="eyebrow">
            {product ? product.brand : 'Untitled product analysis'}
          </p>
          <h2>{product ? product.name : 'What we found'}</h2>
          <p>
            {analysis.summary.parsed_ingredients} ingredients parsed ·{' '}
            {product?.category?.replace('_', ' ') ?? 'personal care'}
          </p>
        </div>
        <Badge variant="outline">
          Database v{analysis.score_breakdown.scoring_version}
        </Badge>
      </div>
      <div className="result-grid">
        <article className="score-block">
          <div className="score-number">
            {analysis.summary.concern_score}
            <small>/100</small>
          </div>
          <p>
            Evidence-backed
            <br />
            concern score
          </p>
          <Badge
            className={`score-status score-status--${analysis.summary.score_band}`}
          >
            {scoreLabel(analysis.summary.score_band)}
          </Badge>
        </article>
        <article className="coverage-block">
          <p className="eyebrow">Analysis coverage</p>
          <strong>{coverage}%</strong>
          <div className="progress-track">
            <span style={{ width: `${coverage}%` }} />
          </div>
          <p>
            {analysis.summary.parsed_ingredients -
              analysis.summary.unknown_ingredients}{' '}
            / {analysis.summary.parsed_ingredients} ingredients matched
          </p>
          {analysis.summary.unknown_ingredients > 0 && (
            <small>
              {analysis.summary.unknown_ingredients} unknown ingredient —
              neutral to score
            </small>
          )}
        </article>
        <article className="alert-block">
          <p className="eyebrow">Personal alerts</p>
          <strong>{analysis.summary.personal_alerts || '—'}</strong>
          <p>
            {personal.length
              ? personal.map((item) => item.canonical_name).join(', ')
              : 'No configured matches'}
          </p>
          {personal.length > 0 && <span>Detected from your profile</span>}
        </article>
      </div>
      {personal.length > 0 && (
        <div className="personal-banner">
          <AlertTriangle size={19} />
          <div>
            <b>Personal alert</b>
            <p>
              {personal[0].canonical_name} was detected as “
              {personal[0].raw_token}” and matches your sensitivity profile.
            </p>
          </div>
        </div>
      )}
      <div className="contributors-layout">
        <section className="contributor-block">
          <div className="section-heading">
            <div>
              <p className="eyebrow">What contributed most?</p>
              <h3>Evidence signals, ranked.</h3>
            </div>
            <CircleHelp size={17} />
          </div>
          {analysis.score_breakdown.top_contributors.length ? (
            <ol>
              {analysis.score_breakdown.top_contributors.map((item, index) => (
                <li key={item.ingredient}>
                  <span>0{index + 1}</span>
                  <b>{item.ingredient}</b>
                  <em>+{item.contribution}</em>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted-copy">
              No configured evidence records contributed to this score.
            </p>
          )}
        </section>
        <section className="evidence-overview">
          <p className="eyebrow">Evidence overview</p>
          <strong>{analysis.summary.high_confidence_flags}</strong>
          <p>high-confidence flags</p>
          <div>
            <span>Regulatory context</span>
            <span>Reference data</span>
            <span>Personal relevance</span>
          </div>
        </section>
      </div>
      <section className="breakdown">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Ingredient breakdown</p>
            <h3>Every term, with context.</h3>
          </div>
          <span>{analysis.summary.parsed_ingredients} total</span>
        </div>
        <div className="ingredient-table" role="list">
          <div className="ingredient-header">
            <span>Ingredient</span>
            <span>Assessment</span>
            <span>Evidence</span>
            <span>Personal</span>
          </div>
          {analysis.ingredients.map((item) => (
            <button
              key={`${item.position}-${item.raw_token}`}
              onClick={() => onSelect(item)}
              className="ingredient-entry"
              role="listitem"
            >
              <span>
                <i
                  className={`signal signal--${item.canonical_name ? tone(item.concern_score) : 'unknown'}`}
                />
                <b>{item.canonical_name ?? item.raw_token}</b>
                {item.canonical_name &&
                  item.canonical_name !== item.raw_token && (
                    <small>{item.raw_token}</small>
                  )}
              </span>
              <span
                className={`assessment assessment--${item.canonical_name ? tone(item.concern_score) : 'unknown'}`}
              >
                {item.canonical_name
                  ? item.concern_score
                    ? 'Review'
                    : 'No flag'
                  : 'Unknown'}
              </span>
              <span>
                {item.canonical_name
                  ? confidence(
                      item.evidence.reduce(
                        (max, evidence) => Math.max(max, evidence.confidence),
                        item.match?.confidence ?? 0,
                      ),
                    )
                  : '—'}
              </span>
              <span>{item.personal_alert ? 'Sensitivity' : '—'}</span>
              <ChevronRight size={17} />
            </button>
          ))}
        </div>
      </section>
      <p className="result-disclaimer">{analysis.disclaimer}</p>
    </section>
  );
}

function RecentPanel({ recent }: { recent: Analysis[] }) {
  return (
    <section className="recent-panel">
      <div>
        <p className="eyebrow">Start here</p>
        <h2>Ask what is inside a product.</h2>
        <p>Paste a label above to receive a structured evidence summary.</p>
      </div>
      {recent.length > 0 && (
        <div className="recent-list">
          <p className="eyebrow">This session</p>
          {recent.map((item) => (
            <div key={item.analysis_id}>
              <b>Untitled analysis</b>
              <span>{item.summary.concern_score} / 100</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function ComparePage({
  onSelect,
  userId,
}: {
  onSelect: (ingredient: Ingredient) => void;
  userId: string;
}) {
  const [a, setA] = useState(''),
    [b, setB] = useState(''),
    [result, setResult] = useState<Comparison | null>(null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState<string | null>(null);
  async function compare() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/comparisons`, {
        method: 'POST',
        headers: accountHeaders(true),
        body: JSON.stringify({
          product_a: {
            ingredient_text: a,
            product_category: 'personal_care',
            user_id: userId,
          },
          product_b: {
            ingredient_text: b,
            product_category: 'personal_care',
            user_id: userId,
          },
        }),
      });
      if (!response.ok) throw new Error();
      setResult(await response.json());
    } catch {
      setError('The comparison could not be completed. Your labels are preserved.');
    } finally {
      setLoading(false);
    }
  }
  return (
    <section className="secondary-page">
      <p className="eyebrow">Compare products</p>
      <h1>
        Put the labels
        <br />
        <span>side by side.</span>
      </h1>
      <p className="lead">
        See evidence-backed differences without reducing either product to a
        blanket safe-or-unsafe judgment.
      </p>
      <div className="compare-composer">
        <Textarea
          aria-label="Product A ingredients"
          value={a}
          onChange={(event) => setA(event.target.value)}
        />
        <Textarea
          aria-label="Product B ingredients"
          value={b}
          onChange={(event) => setB(event.target.value)}
        />
      </div>
      <Button
        className="primary-action compare-button"
        onClick={compare}
        disabled={loading || !a.trim() || !b.trim()}
      >
        {loading ? (
          <LoaderCircle className="animate-spin" />
        ) : (
          'Compare products'
        )}{' '}
        {!loading && <ArrowRight />}
      </Button>
      {error && (
        <div className="error-note" role="alert">
          <AlertTriangle size={18} /> {error}
        </div>
      )}
      {result && (
        <div className="comparison">
          <div className="comparison-cards">
            {[
              { title: 'Product A', data: result.product_a },
              { title: 'Product B', data: result.product_b },
            ].map((card) => (
              <article key={card.title}>
                <p>{card.title}</p>
                <strong>
                  {card.data.summary.concern_score}
                  <small>/100</small>
                </strong>
                <Badge
                  className={`score-status score-status--${card.data.summary.score_band}`}
                >
                  {scoreLabel(card.data.summary.score_band)}
                </Badge>
                <dl>
                  <div>
                    <dt>Coverage</dt>
                    <dd>{Math.round(card.data.summary.coverage * 100)}%</dd>
                  </div>
                  <div>
                    <dt>Personal alerts</dt>
                    <dd>{card.data.summary.personal_alerts}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
          <p className="comparison-note">
            The score difference reflects currently configured evidence records
            and is not a measure of personal safety.
          </p>
          <div className="difference-columns">
            <Difference
              title="Only in product A"
              names={result.only_in_a}
              analysis={result.product_a}
              onSelect={onSelect}
            />
            <Difference
              title="Only in product B"
              names={result.only_in_b}
              analysis={result.product_b}
              onSelect={onSelect}
            />
            <Difference
              title="Shared"
              names={result.shared_ingredients}
              analysis={result.product_a}
              onSelect={onSelect}
            />
          </div>
        </div>
      )}
    </section>
  );
}
function Difference({
  title,
  names,
  analysis,
  onSelect,
}: {
  title: string;
  names: string[];
  analysis: Analysis;
  onSelect: (item: Ingredient) => void;
}) {
  return (
    <article className="difference">
      <p className="eyebrow">{title}</p>
      {names.length ? (
        names.map((name) => {
          const item = analysis.ingredients.find(
            (ingredient) => ingredient.canonical_name === name,
          );
          return (
            <button key={name} onClick={() => item && onSelect(item)}>
              <i
                className={`signal signal--${item ? tone(item.concern_score) : 'calm'}`}
              />
              {name}
            </button>
          );
        })
      ) : (
        <span className="muted-copy">None</span>
      )}
    </article>
  );
}

function HistoryPage({
  onOpen,
  userId,
}: {
  onOpen: (item: HistoryItem) => Promise<void>;
  userId: string;
}) {
  const [tab, setTab] = useState<'products' | 'ingredients'>('products');
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<HistoryItem | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [deleting, setDeleting] = useState(false);
  useEffect(() => {
    void fetch(`${API_BASE}/users/${userId}/history`, {
      headers: accountHeaders(),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        setItems((await response.json()) as HistoryItem[]);
      })
      .catch(() => setError('Your saved history is unavailable right now.'))
      .finally(() => setLoading(false));
  }, [userId]);
  async function deleteItem() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      const response = await fetch(
        `${API_BASE}/users/${userId}/history/${pendingDelete.id}`,
        { method: 'DELETE', headers: accountHeaders() },
      );
      if (!response.ok) throw new Error();
      setItems((current) =>
        current.filter((item) => item.id !== pendingDelete.id),
      );
      setPendingDelete(null);
      setError(null);
    } catch {
      setError('That history item could not be removed.');
    } finally {
      setDeleting(false);
    }
  }
  async function clearHistory() {
    setDeleting(true);
    try {
      const response = await fetch(`${API_BASE}/users/${userId}/history`, {
        method: 'DELETE',
        headers: accountHeaders(),
      });
      if (!response.ok) throw new Error();
      setItems([]);
      setConfirmClear(false);
      setError(null);
    } catch {
      setError('Your history could not be cleared.');
    } finally {
      setDeleting(false);
    }
  }
  const ingredients = useMemo(() => {
    const values = new Map<string, number>();
    items.forEach((item) =>
      item.raw_text
        .split(/[,;\n]/)
        .map((value) => value.trim())
        .filter(Boolean)
        .forEach((ingredient) =>
          values.set(ingredient, (values.get(ingredient) ?? 0) + 1),
        ),
    );
    return [...values.entries()].sort((a, b) => b[1] - a[1]);
  }, [items]);
  return (
    <section className="secondary-page history-page">
      <p className="eyebrow">Your history</p>
      <h1>
        Return to what
        <br />
        <span>you have checked.</span>
      </h1>
      <div className="history-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === 'products'}
          onClick={() => setTab('products')}
          className={tab === 'products' ? 'active' : ''}
        >
          Products
        </button>
        <button
          role="tab"
          aria-selected={tab === 'ingredients'}
          onClick={() => setTab('ingredients')}
          className={tab === 'ingredients' ? 'active' : ''}
        >
          Ingredients
        </button>
        {items.length > 0 && (
          <button className="history-clear" onClick={() => setConfirmClear(true)}>
            Clear history
          </button>
        )}
      </div>
      {error && (
        <div className="error-note" role="alert">
          <AlertTriangle size={18} /> {error}
        </div>
      )}
      {loading ? (
        <div className="analysis-progress">
          <LoaderCircle className="animate-spin" /> Loading saved analyses…
        </div>
      ) : tab === 'products' ? (
        items.length ? (
          <div className="history-grid">
            {items.map((item) => (
              <div className="history-entry" key={item.id}>
                <button
                  onClick={() => void onOpen(item)}
                  className="history-product"
                >
                  <div className="history-product__fallback">
                    {item.product_image_url ? (
                      <img
                        src={
                          item.product_id
                            ? catalogImageUrl(item.product_id)
                            : item.product_image_url
                        }
                        alt={`${item.product_name ?? 'Product'} package`}
                      />
                    ) : (
                      <Layers3 size={20} />
                    )}
                  </div>
                  <div>
                    <span>
                      {item.product_brand ??
                        item.product_source_name ??
                        'Ingredient label'}
                    </span>
                    <h3>{item.product_name ?? 'Ingredient list analysis'}</h3>
                    <p>
                      {Math.round(item.coverage * 100)}% coverage ·{' '}
                      {item.created_at
                        ? new Date(item.created_at).toLocaleDateString()
                        : 'saved analysis'}
                    </p>
                  </div>
                  <strong>
                    {item.concern_score}
                    <small> /100</small>
                  </strong>
                </button>
                <button
                  className="history-delete"
                  aria-label={`Remove ${item.product_name ?? 'analysis'} from history`}
                  onClick={() => setPendingDelete(item)}
                >
                  <X size={16} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <Empty
            icon={<Layers3 />}
            title="No product analyses yet"
            text="Analyze a product to build your saved history."
          />
        )
      ) : ingredients.length ? (
        <div className="history-ingredients">
          {ingredients.map(([ingredient, count], index) => (
            <article key={ingredient}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <b>{ingredient}</b>
              <p>
                Appeared in {count} saved analysis{count === 1 ? '' : 'es'}
              </p>
              <ChevronRight size={17} />
            </article>
          ))}
        </div>
      ) : (
        <Empty
          icon={<Search />}
          title="No ingredient history yet"
          text="Ingredient appearances will show here after an analysis is saved."
        />
      )}
      <Dialog
        open={Boolean(pendingDelete)}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove this history item?</DialogTitle>
            <DialogDescription>
              This removes the saved analysis from your local account. It does
              not remove the catalog product.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingDelete(null)}>
              Keep it
            </Button>
            <Button onClick={() => void deleteItem()} disabled={deleting}>
              {deleting ? <LoaderCircle className="animate-spin" /> : 'Remove'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={confirmClear} onOpenChange={setConfirmClear}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Clear all history?</DialogTitle>
            <DialogDescription>
              This permanently removes every saved product and ingredient-list
              analysis from your local account.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmClear(false)}>
              Cancel
            </Button>
            <Button onClick={() => void clearHistory()} disabled={deleting}>
              {deleting ? <LoaderCircle className="animate-spin" /> : 'Clear history'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
function CatalogPage({
  onAnalyzeProduct,
  userId,
}: {
  onAnalyzeProduct: (product: CatalogProduct) => Promise<void>;
  userId: string;
}) {
  const [query, setQuery] = useState(''),
    [results, setResults] = useState<CatalogProduct[]>([]),
    [loading, setLoading] = useState(false),
    [error, setError] = useState<string | null>(null),
    [emptyMessage, setEmptyMessage] = useState<string | null>(null),
    [analyzing, setAnalyzing] = useState<string | null>(null),
    [scanning, setScanning] = useState(false);
  const [reportProduct, setReportProduct] = useState<CatalogProduct | null>(
      null,
    ),
    [reportReason, setReportReason] = useState('outdated_label'),
    [reportDetails, setReportDetails] = useState(''),
    [reporting, setReporting] = useState(false),
    [reportNotice, setReportNotice] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const frame = useRef<number | null>(null);
  const stopScanner = () => {
    if (frame.current) cancelAnimationFrame(frame.current);
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    setScanning(false);
  };
  useEffect(() => () => stopScanner(), []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    void fetch(`${API_BASE}/products?limit=120`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const products = (await response.json()) as CatalogProduct[];
        setResults(products);
        setEmptyMessage(
          products.length
            ? null
            : 'The catalog is ready, but it does not contain any stored products yet.',
        );
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === 'AbortError') return;
        setError('The product catalog is unavailable right now.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);
  async function search(value = query, barcode = false) {
    setLoading(true);
    setError(null);
    setEmptyMessage(null);
    try {
      const trimmed = value.trim();
      const parameter = barcode ? 'barcode' : 'query';
      const endpoint = trimmed
        ? `${API_BASE}/products?${parameter}=${encodeURIComponent(trimmed)}`
        : `${API_BASE}/products?limit=120`;
      const response = await fetch(endpoint);
      if (!response.ok) throw new Error();
      const next = (await response.json()) as CatalogProduct[];
      const resultStatus = response.headers.get('X-Catalog-Result');
      setResults(next);
      if (!next.length)
        setEmptyMessage(
          resultStatus === 'external_unavailable'
            ? 'The external catalog is temporarily unavailable. Try again shortly or paste the ingredient label.'
            : 'No catalog product matched that search. Try the product name, company, or barcode.',
        );
    } catch {
      setError('The product catalog is unavailable right now.');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }
  async function startScanner() {
    const Detector = (
      window as unknown as {
        BarcodeDetector?: new (options?: { formats?: string[] }) => {
          detect: (source: HTMLVideoElement) => Promise<{ rawValue: string }[]>;
        };
      }
    ).BarcodeDetector;
    if (!Detector || !navigator.mediaDevices?.getUserMedia) {
      setError(
        'Camera barcode scanning is not supported in this browser. Enter the barcode number instead.',
      );
      return;
    }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
        audio: false,
      });
      if (!video.current) return;
      video.current.srcObject = stream.current;
      await video.current.play();
      setScanning(true);
      const detector = new Detector({
        formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128'],
      });
      const detect = async () => {
        if (!video.current) return;
        const codes = await detector.detect(video.current);
        if (codes[0]?.rawValue) {
          const value = codes[0].rawValue;
          setQuery(value);
          stopScanner();
          void search(value, true);
          return;
        }
        frame.current = requestAnimationFrame(() => void detect());
      };
      void detect();
    } catch {
      stopScanner();
      setError(
        'We could not access the camera. Check browser permission or enter the barcode number.',
      );
    }
  }
  async function selectProduct(product: CatalogProduct) {
    setAnalyzing(product.id);
    try {
      await onAnalyzeProduct(product);
    } finally {
      setAnalyzing(null);
    }
  }
  async function submitReport() {
    if (!reportProduct) return;
    setReporting(true);
    try {
      const response = await fetch(
        `${API_BASE}/products/${reportProduct.id}/reports`,
        {
          method: 'POST',
          headers: accountHeaders(true),
          body: JSON.stringify({
            user_id: userId,
            reason: reportReason,
            details: reportDetails.trim() || null,
          }),
        },
      );
      if (!response.ok) throw new Error();
      setReportProduct(null);
      setReportDetails('');
      setReportNotice('Thanks — the catalog record was flagged for review.');
    } catch {
      setReportNotice('The report could not be saved. Please try again.');
    } finally {
      setReporting(false);
    }
  }
  return (
    <section className="secondary-page catalog-page">
      <p className="eyebrow">Product catalog</p>
      <h1>
        Search a product
        <br />
        <span>or its company.</span>
      </h1>
      <p className="lead">
        Find a catalog label by its product name, company, or barcode, then
        analyze the recorded ingredient list.
      </p>
      <form
        className="search-field"
        onSubmit={(event) => {
          event.preventDefault();
          void search();
        }}
      >
        <Search size={18} />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search products, companies, or barcodes"
        />
        <Button
          type="button"
          variant="outline"
          onClick={() => void startScanner()}
          aria-label="Scan barcode with camera"
        >
          <Camera size={17} />
        </Button>
        <Button type="submit" disabled={loading}>
          {loading ? 'Searching…' : 'Search'}
        </Button>
      </form>
      {scanning && (
        <div className="barcode-scanner">
          <video ref={video} muted playsInline />
          <Button variant="outline" onClick={stopScanner}>
            Stop camera
          </Button>
        </div>
      )}
      <p className="catalog-note">
        Catalog records show where their product information came from.
        Ingredient labels can change, so verify a product label before relying
        on an analysis.
      </p>
      {!loading && results.length > 0 && (
        <p className="catalog-count" role="status">
          {results.length} stored {results.length === 1 ? 'product' : 'products'}
        </p>
      )}
      {reportNotice && (
        <p className="composer-hint" role="status">
          <Sparkles size={14} /> {reportNotice}
        </p>
      )}
      {error && (
        <div className="error-note" role="alert">
          <AlertTriangle size={18} /> {error}
        </div>
      )}
      <div className="explorer-results catalog-results">
        {results.map((item) => (
          <article key={item.id}>
            <div className="catalog-product-mark">
              {item.image_url ? (
                <img
                  src={catalogImageUrl(item.id)}
                  alt={`${item.name} package`}
                  loading="lazy"
                />
              ) : (
                <Layers3 size={20} />
              )}
            </div>
            <div className="catalog-card-body">
              <p className="eyebrow">
                {item.brand} · {item.category?.replace('_', ' ') ?? 'Product'}
              </p>
              <h3>{item.name}</h3>
              <p>{item.description}</p>
              <div className="catalog-provenance">
                {item.source_url ? (
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="catalog-source-link"
                  >
                    {item.source_name}
                  </a>
                ) : (
                  <Badge variant="outline">Demo catalog record</Badge>
                )}
                {item.label_verified_at && (
                  <small>
                    Label verified{' '}
                    {new Date(item.label_verified_at).toLocaleDateString()}
                  </small>
                )}
              </div>
              <small className="catalog-ingredients">
                {item.ingredient_text}
              </small>
            </div>
            <div className="catalog-card-actions">
              <Button
                variant="ghost"
                onClick={() => {
                  setReportProduct(item);
                  setReportNotice(null);
                }}
              >
                Report data
              </Button>
              <Button
                variant="outline"
                onClick={() => void selectProduct(item)}
                disabled={analyzing !== null}
              >
                {analyzing === item.id ? (
                  <LoaderCircle className="animate-spin" />
                ) : (
                  'Analyze'
                )}
              </Button>
            </div>
          </article>
        ))}
      </div>
      {query && !loading && !results.length && (
        <Empty
          icon={<Search />}
          title={
            emptyMessage?.startsWith('The external')
              ? 'Catalog temporarily unavailable'
              : 'No matching product'
          }
          text={
            emptyMessage ?? 'Try a different product name, company, or barcode.'
          }
        />
      )}
      <Dialog
        open={Boolean(reportProduct)}
        onOpenChange={(open) => !open && setReportProduct(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Report catalog data</DialogTitle>
            <DialogDescription>
              Flag an incorrect or outdated record for review. This does not
              change the product immediately.
            </DialogDescription>
          </DialogHeader>
          <label htmlFor="catalog-report-reason">
            Reason
            <NativeSelect
              id="catalog-report-reason"
              className="w-full"
              value={reportReason}
              onChange={(event) => setReportReason(event.target.value)}
            >
              <NativeSelectOption value="outdated_label">
                Outdated label
              </NativeSelectOption>
              <NativeSelectOption value="incorrect_ingredients">
                Incorrect ingredients
              </NativeSelectOption>
              <NativeSelectOption value="wrong_product">
                Wrong product details
              </NativeSelectOption>
              <NativeSelectOption value="duplicate">
                Duplicate record
              </NativeSelectOption>
              <NativeSelectOption value="other">Other</NativeSelectOption>
            </NativeSelect>
          </label>
          <label htmlFor="catalog-report-details">
            Details
            <Textarea
              id="catalog-report-details"
              value={reportDetails}
              onChange={(event) => setReportDetails(event.target.value)}
            />
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReportProduct(null)}>
              Cancel
            </Button>
            <Button onClick={() => void submitReport()} disabled={reporting}>
              {reporting ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                'Submit report'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
function ProfilePage({
  name,
  preferences,
  profile,
  userId,
  onSave,
  onDelete,
  onSaveProfile,
}: {
  name: string;
  preferences: Preference[];
  profile: UserProfile | null;
  userId: string;
  onSave: (ingredient: string) => Promise<void>;
  onDelete: (ingredientId: string) => Promise<void>;
  onSaveProfile: (profile: UserProfile) => Promise<UserProfile>;
}) {
  const [input, setInput] = useState('');
  const [form, setForm] = useState<UserProfile>({
    user_id: userId,
    display_name: name || null,
    avatar_url: null,
    dietary_preferences: [],
    cultural_considerations: [],
    additional_requirements: null,
  });
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    if (profile) setForm(profile);
  }, [profile]);
  async function add() {
    if (input.trim()) {
      try {
        await onSave(input.trim());
        setInput('');
        setNotice('Ingredient preference saved.');
      } catch {
        setNotice('We could not save that ingredient preference.');
      }
    }
  }
  async function remove(ingredientId: string) {
    try {
      await onDelete(ingredientId);
      setNotice('Ingredient preference removed.');
    } catch {
      setNotice('We could not remove that ingredient preference.');
    }
  }
  async function save() {
    setSaving(true);
    setNotice(null);
    try {
      await onSaveProfile(form);
      setNotice('Profile saved.');
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : 'We could not save your profile.',
      );
    } finally {
      setSaving(false);
    }
  }
  async function chooseAvatar(file: File) {
    if (!file.type.startsWith('image/') || file.size > 1_500_000) {
      setNotice('Choose an image under 1.5 MB.');
      return;
    }
    const reader = new FileReader();
    reader.onload = () =>
      setForm((current) => ({
        ...current,
        avatar_url:
          typeof reader.result === 'string'
            ? reader.result
            : current.avatar_url,
      }));
    reader.readAsDataURL(file);
  }
  return (
    <section className="secondary-page profile-page">
      <p className="eyebrow">Your profile</p>
      <h1>
        Your context,
        <br />
        <span>in your control.</span>
      </h1>
      <p className="lead">
        Update your personal safety context at any time. These details are shown
        separately from general product evidence.
      </p>
      <div className="profile-layout">
        <section className="account-card">
          <div className="avatar-editor">
            {form.avatar_url ? (
              <img src={form.avatar_url} alt="Profile preview" />
            ) : (
              <UserRound size={30} />
            )}
            <label>
              <input
                type="file"
                accept="image/*"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void chooseAvatar(file);
                }}
              />
              Change photo
            </label>
          </div>
          <div>
            <b>{form.display_name || name || 'Your account'}</b>
            <span>Personal account</span>
          </div>
        </section>
        <section className="profile-card safety-card">
          <p className="eyebrow">
            Allergens, irritations & avoided ingredients
          </p>
          <h3>What should be highlighted?</h3>
          <div className="profile-input">
            <Search size={17} />
            <Input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) =>
                event.key === 'Enter' && (event.preventDefault(), void add())
              }
            />
            <Button size="sm" onClick={() => void add()}>
              Add
            </Button>
          </div>
          <div className="chip-list">
            {preferences.length ? (
              preferences.map((item) => (
                <span className="chip" key={item.ingredient_id}>
                  {item.canonical_name}
                  <button
                    aria-label={`Remove ${item.canonical_name}`}
                    onClick={() => void remove(item.ingredient_id)}
                  >
                    <X size={13} />
                  </button>
                </span>
              ))
            ) : (
              <p className="muted-copy">No saved ingredient matches yet.</p>
            )}
          </div>
        </section>
        <section className="profile-card">
          <p className="eyebrow">Account details</p>
          <h3>Name</h3>
          <Input
            value={form.display_name ?? ''}
            onChange={(event) =>
              setForm({ ...form, display_name: event.target.value || null })
            }
          />
        </section>
        <section className="profile-card">
          <p className="eyebrow">Dietary pattern</p>
          <h3>Food choices</h3>
          <Input
            value={form.dietary_preferences.join(', ')}
            onChange={(event) =>
              setForm({
                ...form,
                dietary_preferences: event.target.value
                  .split(',')
                  .map((value) => value.trim())
                  .filter(Boolean),
              })
            }
          />
          <p className="profile-help">
            Separate choices with commas: vegetarian, vegan, gluten-free.
          </p>
        </section>
        <section className="profile-card">
          <p className="eyebrow">Cultural & religious considerations</p>
          <h3>Values to respect</h3>
          <Input
            value={form.cultural_considerations.join(', ')}
            onChange={(event) =>
              setForm({
                ...form,
                cultural_considerations: event.target.value
                  .split(',')
                  .map((value) => value.trim())
                  .filter(Boolean),
              })
            }
          />
        </section>
        <section className="profile-card">
          <p className="eyebrow">Additional safety context</p>
          <h3>Anything else to remember?</h3>
          <Textarea
            value={form.additional_requirements ?? ''}
            onChange={(event) =>
              setForm({
                ...form,
                additional_requirements: event.target.value || null,
              })
            }
          />
        </section>
      </div>
      {notice && (
        <p className="composer-hint" role="status">
          <Sparkles size={14} /> {notice}
        </p>
      )}
      <Button
        className="primary-action"
        onClick={() => void save()}
        disabled={saving}
      >
        {saving ? <LoaderCircle className="animate-spin" /> : 'Save profile'}
      </Button>
    </section>
  );
}
function Empty({
  icon,
  title,
  text,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <div className="empty-state">
      {icon}
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}

function IngredientDrawer({
  ingredient,
  onClose,
  onSave,
}: {
  ingredient: Ingredient | null;
  onClose: () => void;
  onSave: (ingredient: string) => Promise<void>;
}) {
  return (
    <Sheet
      open={Boolean(ingredient)}
      onOpenChange={(open) => !open && onClose()}
    >
      <SheetContent side="right" className="drawer">
        <>
          {ingredient && (
            <>
              <SheetHeader className="drawer-head">
                <p className="eyebrow">Ingredient evidence</p>
                <SheetTitle className="drawer-title">
                  {ingredient.canonical_name ?? ingredient.raw_token}
                </SheetTitle>
                <SheetDescription>
                  {ingredient.canonical_name
                    ? `Detected as “${ingredient.raw_token}” on the label.`
                    : 'This term could not be confidently mapped to a canonical ingredient.'}
                </SheetDescription>
              </SheetHeader>
              <div className="drawer-body">
                {ingredient.canonical_name && (
                  <Button
                    variant="outline"
                    className="preference-button"
                    onClick={() => onSave(ingredient.canonical_name!)}
                  >
                    <Plus /> Add to sensitivity list
                  </Button>
                )}
                {ingredient.personal_alert && (
                  <div className="personal-banner compact">
                    <AlertTriangle size={18} />
                    <div>
                      <b>Personal alert</b>
                      <p>{ingredient.personal_alert.message}</p>
                    </div>
                  </div>
                )}
                {ingredient.evidence.length ? (
                  <>
                    <section>
                      <p className="eyebrow">Assessment</p>
                      <h3>
                        {ingredient.concern_score
                          ? 'Evidence requires context.'
                          : 'No configured concern flag.'}
                      </h3>
                      <p className="drawer-copy">
                        A listed ingredient is not a measure of dose,
                        absorption, or outcome. Review the source context and
                        limitations.
                      </p>
                    </section>
                    <section>
                      <p className="eyebrow">Source records</p>
                      {ingredient.evidence.map((record, index) => (
                        <article
                          className="source-record"
                          key={`${record.source_name}-${index}`}
                        >
                          <div>
                            <b>{record.source_name}</b>
                            <Badge variant="outline">
                              {confidence(record.confidence)}
                            </Badge>
                          </div>
                          <p>{record.summary}</p>
                          <dl>
                            <div>
                              <dt>Concern</dt>
                              <dd>{record.concern_type}</dd>
                            </div>
                            <div>
                              <dt>Context</dt>
                              <dd>{record.applicability.replace('_', ' ')}</dd>
                            </div>
                          </dl>
                          {record.limitations && (
                            <small>
                              <b>Limitations:</b> {record.limitations}
                            </small>
                          )}
                          {record.source_url && (
                            <a
                              href={record.source_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open source <ArrowRight size={14} />
                            </a>
                          )}
                        </article>
                      ))}
                    </section>
                  </>
                ) : (
                  <Empty
                    icon={<Search />}
                    title={
                      ingredient.canonical_name
                        ? 'No evidence records yet'
                        : 'Unknown does not mean harmful'
                    }
                    text={
                      ingredient.canonical_name
                        ? 'This ingredient is recognized, but the local evidence set has no active records for it.'
                        : 'It did not match the current database with enough confidence and has not increased the score.'
                    }
                  />
                )}
              </div>
            </>
          )}
        </>
      </SheetContent>
    </Sheet>
  );
}
