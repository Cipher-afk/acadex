--
-- PostgreSQL database dump
--

\restrict KYQze9hVtx3NAoozyz19zIWKJkmFXB8gSZ0HlEujLAJ8vshl27f8ggYzFVcaJ8Q

-- Dumped from database version 15.17 (Debian 15.17-1.pgdg13+1)
-- Dumped by pg_dump version 15.17 (Debian 15.17-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO postgres;

--
-- Name: marketer; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.marketer (
    telegram_id character varying NOT NULL,
    username character varying NOT NULL,
    password character varying NOT NULL,
    amount_paid integer NOT NULL,
    subscribed boolean NOT NULL
);


ALTER TABLE public.marketer OWNER TO postgres;

--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    telegram_id character varying NOT NULL,
    user_id character varying NOT NULL,
    is_paid boolean DEFAULT false,
    level integer NOT NULL,
    expiry date,
    referrer character varying
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.alembic_version (version_num) FROM stdin;
d1e0e1bd6902
\.


--
-- Data for Name: marketer; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.marketer (telegram_id, username, password, amount_paid, subscribed) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (telegram_id, user_id, is_paid, level, expiry, referrer) FROM stdin;
603697634	Peremoboere.eyedekeme	f	300	2026-10-16	\N
6812949758	deborah.adefemi	f	200	2026-10-16	\N
8737692862	marvellous.ndianabasi	f	200	2026-10-17	\N
7352060440	ayamaman.johnnie	f	100	2026-10-17	\N
6960784154	joy.edwin	f	300	2026-10-17	\N
7142613083	marvel.dienagha	f	300	2026-10-19	\N
5067071298	Faith.barile	f	300	2026-10-22	\N
8736003518	Promise.nwokeiwu	t	100	2026-10-25	\N
6592231722	olaguazibe.obein	f	200	2026-10-25	\N
8781330937	oyindeinmone.court	f	300	2026-10-25	\N
6256444116	rejoice.alabo	f	300	2026-10-25	\N
7542179790	Kelvin.agonoh	f	7	2026-10-25	\N
7936016523	gede.john	f	300	2026-10-26	\N
5319301010	ogheneteguono.igoru	f	500	2027-04-26	\N
7973361517	nimi.doumoyo	f	400	2026-10-18	\N
1966820494	John.gede	t	300	2026-10-26	\N
6299600067	david.sonlo	t	100	2026-10-26	\N
7928624104	tamunomiebaka.belema	f	400	2026-10-16	\N
8710513612	Solomon	f	300	2026-10-26	\N
5332904327	godson.enoya	t	200	2026-10-26	\N
6939476006	Olavourkere.edighotu	t	100	2026-10-26	\N
6844319332	Gibson.ayawei	f	300	2026-10-27	\N
5274907729	Louis.oguname	t	6	2026-10-28	\N
8071264858	daniel.stephen2	f	200	2026-10-29	\N
6323004754	Ekpakanumu.Wapaebiama	t	100	2026-10-26	\N
5571024854	Paul.agama	f	300	2026-12-03	\N
8625068141	tamarapreye.akanyo1	f	100	2026-12-03	\N
6939896602	Samuel. Simple	f	300	2026-12-03	\N
7719177970	godspower.okadu	f	300	2026-12-03	\N
7112142863	Micheal.olanrewaju	t	300	2026-10-20	\N
7475407252	Precious.jonathan1	t	300	2026-11-12	\N
7647451975	Prosper.Tom-isele	f	100	2026-12-03	\N
5685508702	/download_results	f	200	2026-12-03	\N
8293672510	woyengikuro.binalayefa	f	300	2026-12-03	\N
6873269025	bright.brown	f	400	2026-12-03	\N
5662162911	Ezekiel.allison	f	200	2026-12-03	\N
7128052016	blessing.amakiri	f	400	2026-12-03	\N
6938713778	Believe Adezor	f	300	2026-12-03	\N
8557003864	Victor.ojo	f	300	2026-12-03	\N
6957097563	joshua.igburu	t	300	2026-12-03	\N
1307189717	triumph.emmanuel	t	200	2026-12-03	\N
5233545484	/download_results	t	400	2026-12-03	\N
7476392426	eke	f	100	2026-12-04	\N
6887731188	Precious.amon	f	100	2026-12-04	\N
6385978967	woyengimiesindou.ogiri	t	100	2026-12-04	\N
7531622585	Tarimobowei.Shellowei	f	300	2026-12-04	\N
7138442080	Emmanuel.patrick	f	200	2026-12-04	\N
6046973878	olajuwon.aturu	t	300	2026-12-04	\N
8485748052	douye.humphrey	f	300	2026-12-06	\N
5050380486	cross.akpotu	t	300	2026-12-03	\N
6465984646	Caleb.ifeji	f	600	2027-04-06	\N
6938534381	ebiyebode.asemota	f	400	2027-04-20	\N
8043673543	Ogheneyole.john	f	300	2027-04-20	\N
7523246596	Daniel.prince	f	200	2027-04-20	\N
7179954973	soibifa-a . biobele	f	300	2027-04-20	\N
8653353656	destiny.gbenebro	f	400	2027-04-21	\N
6214702998	Prince.tautua	f	400	2027-04-21	\N
5009575015	godbless.adesefuobo	t	400	2027-04-21	\N
9108470420	Kenechukwu.Chima	f	300	2027-04-20	\N
8784511958	amachreesamuel8@gmail.com	f	200	2027-04-24	\N
8842446589	nzemirian66@gmail.com	f	200	2027-04-26	\N
\.


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: marketer marketer_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.marketer
    ADD CONSTRAINT marketer_pkey PRIMARY KEY (telegram_id);


--
-- Name: marketer marketer_username_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.marketer
    ADD CONSTRAINT marketer_username_key UNIQUE (username);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (telegram_id);


--
-- Name: users users_referrer_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_referrer_fkey FOREIGN KEY (referrer) REFERENCES public.marketer(username);


--
-- PostgreSQL database dump complete
--

\unrestrict KYQze9hVtx3NAoozyz19zIWKJkmFXB8gSZ0HlEujLAJ8vshl27f8ggYzFVcaJ8Q

