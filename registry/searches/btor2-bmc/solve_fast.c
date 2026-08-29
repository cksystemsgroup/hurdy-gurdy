/* solve_fast.c — the btor2-bmcf accelerator, revision 4:
 * the caps learn the accelerator's pace (wall-derived budget and
 * structural ceilings with absolute memory bounds); otherwise
 * identical to revision 3:
 * the mirror learns arrays — read, write, array ite, extensional
 * eq/neq by the eager reduction (hash-consed array terms, Ackermann
 * congruence, skolem-witness extensionality), nested arrays refused
 * with a partial. The witness self-check is interpreter-faithful:
 * array-equality leaves and base-select leaves are pinned to their
 * concrete canonical-array values (built from the extracted stimulus)
 * and the circuit is re-evaluated to fixpoint over the DAG, so the
 * replay verdict — and therefore every byte — matches the reference
 * even where the sparse instantiation and the interpreter disagree.
 *
 * A C mirror of the reference solve.py: same parser, same
 * demand-driven AIG blasting (identical node creation order), same
 * CDCL solver (two-watched literals, 1UIP, VSIDS with IEEE-double
 * activities, CPython-heapq decision order, identical restart and
 * budget arithmetic), same witness extraction and JSON rendering —
 * so that for every invocation the bytes on stdout equal the
 * reference's bytes. The reference remains the semantics; this file
 * is only a cheaper route to the same output.
 *
 * Build: cc -O2 -o solve_fast solve_fast.c
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

static void die(const char *msg) { fprintf(stderr, "%s\n", msg); exit(1); }

/* ---------------- growable vectors ---------------- */
#define VEC(T) struct { T *d; int n, cap; }
typedef struct { int *d; int n, cap; } IVec;
#define vpush(v, x) do { \
    if ((v).n == (v).cap) { \
        (v).cap = (v).cap ? (v).cap * 2 : 8; \
        (v).d = realloc((v).d, sizeof(*(v).d) * (size_t)(v).cap); \
        if (!(v).d) die("oom"); } \
    (v).d[(v).n++] = (x); } while (0)

/* ---------------- parser ---------------- */
enum {
    OP_CONST, OP_INPUT, OP_STATE, OP_ITE, OP_SLICE, OP_UEXT, OP_SEXT,
    OP_CONCAT, OP_NOT, OP_NEG, OP_INC, OP_DEC, OP_REDAND, OP_REDOR,
    OP_REDXOR, OP_AND, OP_OR, OP_XOR, OP_NAND, OP_NOR, OP_XNOR,
    OP_IMPLIES, OP_IFF, OP_EQ, OP_NEQ, OP_ULT, OP_ULTE, OP_UGT,
    OP_UGTE, OP_SLT, OP_SLTE, OP_SGT, OP_SGTE, OP_ADD, OP_SUB, OP_MUL,
    OP_UDIV, OP_UREM, OP_SLL, OP_SRL, OP_SRA, OP_SDIV, OP_SREM,
    OP_SMOD, OP_READ, OP_WRITE, OP_NONE
};

static const struct { const char *name; int op; } OPTAB[] = {
    {"ite", OP_ITE}, {"slice", OP_SLICE}, {"uext", OP_UEXT},
    {"sext", OP_SEXT}, {"concat", OP_CONCAT}, {"not", OP_NOT},
    {"neg", OP_NEG}, {"inc", OP_INC}, {"dec", OP_DEC},
    {"redand", OP_REDAND}, {"redor", OP_REDOR}, {"redxor", OP_REDXOR},
    {"and", OP_AND}, {"or", OP_OR}, {"xor", OP_XOR}, {"nand", OP_NAND},
    {"nor", OP_NOR}, {"xnor", OP_XNOR}, {"implies", OP_IMPLIES},
    {"iff", OP_IFF}, {"eq", OP_EQ}, {"neq", OP_NEQ}, {"ult", OP_ULT},
    {"ulte", OP_ULTE}, {"ugt", OP_UGT}, {"ugte", OP_UGTE},
    {"slt", OP_SLT}, {"slte", OP_SLTE}, {"sgt", OP_SGT},
    {"sgte", OP_SGTE}, {"add", OP_ADD}, {"sub", OP_SUB},
    {"mul", OP_MUL}, {"udiv", OP_UDIV}, {"urem", OP_UREM},
    {"sll", OP_SLL}, {"srl", OP_SRL}, {"sra", OP_SRA},
    {"sdiv", OP_SDIV}, {"srem", OP_SREM}, {"smod", OP_SMOD},
    {"read", OP_READ}, {"write", OP_WRITE}, {NULL, 0}
};

#define MAXID 2000000

typedef struct {
    int op;            /* OP_* or OP_NONE                  */
    int width;
    long long a[3];    /* refs (signed) or immediates      */
    int na;
    uint8_t *cbits;    /* OP_CONST: width bits             */
    uint8_t is_arr;    /* array-sorted node                */
    int aiw, aew;      /* its index and element widths     */
} Node;

/* the reference wraps parse+bmc in try/except ValueError and emits a
 * partial with the message — mirrored for every reachable message */
static void partial_exit(const char *note) {
    printf("{\"kind\": \"partial\", \"progress\": {\"note\": \"%s\"}}\n",
           note);
    exit(0);
}

static int have_arrays;

static Node *nodes;                /* by id */
static int max_id;
static VEC(int) order;             /* node ids, file order   */
static VEC(int) inputs_v, states_v;
static long long *init_ref, *next_ref;  /* by state id; LLONG_MIN = none */
static uint8_t *has_init, *has_next;
static VEC(long long) bads_v, constraints_v;

#define NOREF ((long long)0x8000000000000000LL)

/* decimal string -> bit array (two's complement into width bits) */
static void dec_to_bits(const char *s, uint8_t *bits, int width) {
    int neg = 0;
    if (*s == '-') { neg = 1; s++; }
    else if (*s == '+') s++;
    int len = (int)strlen(s);
    uint8_t *dig = malloc((size_t)len);
    for (int i = 0; i < len; i++) {
        if (s[i] < '0' || s[i] > '9') die("bad constd");
        dig[i] = (uint8_t)(s[i] - '0');
    }
    memset(bits, 0, (size_t)width);
    int start = 0;
    for (int b = 0; b < width; b++) {
        while (start < len && dig[start] == 0) start++;
        if (start >= len) break;
        /* divide digit string by 2, remainder is the next bit */
        int rem = 0;
        for (int i = start; i < len; i++) {
            int cur = rem * 10 + dig[i];
            dig[i] = (uint8_t)(cur / 2);
            rem = cur & 1;
        }
        bits[b] = (uint8_t)rem;
    }
    free(dig);
    if (neg) {                    /* two's complement negate */
        for (int b = 0; b < width; b++) bits[b] ^= 1;
        int carry = 1;
        for (int b = 0; b < width && carry; b++) {
            int v = bits[b] + carry;
            bits[b] = (uint8_t)(v & 1);
            carry = v >> 1;
        }
    }
}

static void parse_file(const char *path) {
    FILE *fh = fopen(path, "r");
    if (!fh) die("cannot open program");
    nodes = calloc(MAXID, sizeof(Node));
    init_ref = malloc(MAXID * sizeof(long long));
    next_ref = malloc(MAXID * sizeof(long long));
    has_init = calloc(MAXID, 1);
    has_next = calloc(MAXID, 1);
    int *sortw = calloc(MAXID, sizeof(int));
    int *sort_aiw = calloc(MAXID, sizeof(int));
    int *sort_aew = calloc(MAXID, sizeof(int));
    uint8_t *sort_isarr = calloc(MAXID, 1);
    if (!nodes || !init_ref || !next_ref || !sortw
        || !sort_aiw || !sort_aew || !sort_isarr) die("oom");
    for (int i = 0; i < MAXID; i++) nodes[i].op = OP_NONE;
    char line[1 << 16];
    while (fgets(line, sizeof line, fh)) {
        char *semi = strchr(line, ';');
        if (semi) *semi = 0;
        char *tok[64];
        int nt = 0;
        for (char *p = strtok(line, " \t\r\n"); p && nt < 64;
             p = strtok(NULL, " \t\r\n"))
            tok[nt++] = p;
        if (nt == 0) continue;
        long long nid = atoll(tok[0]);
        if (nid <= 0 || nid >= MAXID) die("id out of range");
        const char *op = tok[1];
        if (!strcmp(op, "sort")) {
            if (!strcmp(tok[2], "bitvec")) {
                sortw[nid] = atoi(tok[3]);
            } else if (!strcmp(tok[2], "array")) {
                long long isid = atoll(tok[3]), esid = atoll(tok[4]);
                if (sort_isarr[esid])
                    partial_exit("nested arrays: outside this "
                                 "solver's fragment");
                if (sort_isarr[isid]) die("array index sort is an array");
                sort_isarr[nid] = 1;
                sort_aiw[nid] = sortw[isid];
                sort_aew[nid] = sortw[esid];
            } else {
                char buf[96];
                snprintf(buf, sizeof buf, "unsupported sort: %.60s",
                         tok[2]);
                partial_exit(buf);
            }
            continue;
        }
        if (!strcmp(op, "init")) {
            init_ref[atoll(tok[3])] = atoll(tok[4]);
            has_init[atoll(tok[3])] = 1;
            continue;
        }
        if (!strcmp(op, "next")) {
            next_ref[atoll(tok[3])] = atoll(tok[4]);
            has_next[atoll(tok[3])] = 1;
            continue;
        }
        if (!strcmp(op, "bad")) { vpush(bads_v, atoll(tok[2])); continue; }
        if (!strcmp(op, "constraint")) {
            vpush(constraints_v, atoll(tok[2]));
            continue;
        }
        if (!strcmp(op, "output") || !strcmp(op, "fair")
                || !strcmp(op, "justice"))
            continue;
        long long sid_ = atoll(tok[2]);
        int w = sortw[sid_];
        Node *nd = &nodes[nid];
        nd->width = w;
        if (sort_isarr[sid_]) {
            nd->is_arr = 1;
            nd->aiw = sort_aiw[sid_];
            nd->aew = sort_aew[sid_];
            have_arrays = 1;
        }
        if (nid > max_id) max_id = (int)nid;
        if (!strcmp(op, "input")) {
            nd->op = OP_INPUT;
            vpush(inputs_v, (int)nid);
        } else if (!strcmp(op, "state")) {
            nd->op = OP_STATE;
            vpush(states_v, (int)nid);
        } else if (!strcmp(op, "const") || !strcmp(op, "constd")
                   || !strcmp(op, "consth") || !strcmp(op, "zero")
                   || !strcmp(op, "one") || !strcmp(op, "ones")) {
            nd->op = OP_CONST;
            nd->cbits = calloc((size_t)w, 1);
            if (!strcmp(op, "zero")) { }
            else if (!strcmp(op, "one")) { if (w) nd->cbits[0] = 1; }
            else if (!strcmp(op, "ones")) memset(nd->cbits, 1, (size_t)w);
            else if (!strcmp(op, "const")) {
                int len = (int)strlen(tok[3]);
                for (int i = 0; i < len && i < w; i++)
                    nd->cbits[i] = (uint8_t)(tok[3][len - 1 - i] - '0');
            } else if (!strcmp(op, "consth")) {
                int len = (int)strlen(tok[3]);
                for (int i = 0; i < len; i++) {
                    char c = tok[3][len - 1 - i];
                    int v = c <= '9' ? c - '0'
                        : c <= 'F' ? c - 'A' + 10 : c - 'a' + 10;
                    for (int b = 0; b < 4; b++)
                        if (4 * i + b < w)
                            nd->cbits[4 * i + b] =
                                (uint8_t)((v >> b) & 1);
                }
            } else {
                dec_to_bits(tok[3], nd->cbits, w);
            }
        } else {
            int found = -1;
            for (int i = 0; OPTAB[i].name; i++)
                if (!strcmp(op, OPTAB[i].name)) { found = OPTAB[i].op; break; }
            if (found < 0) {
                char buf[96];
                snprintf(buf, sizeof buf, "unsupported op: %.60s", op);
                partial_exit(buf);
            }
            nd->op = found;
            int want = found == OP_ITE ? 3
                : found == OP_WRITE ? 3
                : found == OP_SLICE ? 3
                : (found == OP_UEXT || found == OP_SEXT) ? 2
                : (found >= OP_NOT && found <= OP_REDXOR) ? 1 : 2;
            for (int i = 0; i < want; i++) {
                char *end;
                long long v = strtoll(tok[3 + i], &end, 10);
                if (*end) die("bad operand");
                nd->a[i] = v;
            }
            nd->na = want;
        }
        vpush(order, (int)nid);
    }
    fclose(fh);
    free(sortw);
    free(sort_aiw);
    free(sort_aew);
    free(sort_isarr);
}

/* ---------------- AIG ---------------- */
typedef struct { uint32_t a, b; } Gate;
static VEC(Gate) gnodes;               /* node 0 = const false */
static uint32_t *ghash;
static uint32_t ghash_mask;
static int ghash_used;

static void ghash_grow(void);

static void aig_init(void) {
    Gate g0 = {0, 0};
    vpush(gnodes, g0);                 /* placeholder for node 0 */
    ghash_mask = (1 << 20) - 1;
    ghash = calloc((size_t)ghash_mask + 1, sizeof(uint32_t));
}

static uint32_t aig_var(void) {
    Gate g = {0xffffffffu, 0xffffffffu};   /* leaf marker */
    vpush(gnodes, g);
    return 2u * (uint32_t)(gnodes.n - 1);
}

static void ghash_grow(void) {
    uint32_t nm = ghash_mask * 2 + 1;
    uint32_t *nh = calloc((size_t)nm + 1, sizeof(uint32_t));
    for (uint32_t i = 0; i <= ghash_mask; i++) {
        uint32_t lit = ghash[i];
        if (!lit) continue;
        Gate g = gnodes.d[lit >> 1];
        uint64_t key = ((uint64_t)g.a << 32) | g.b;
        uint64_t h = key * 0x9E3779B97F4A7C15ull;
        uint32_t pos = (uint32_t)(h >> 32) & nm;
        while (nh[pos]) pos = (pos + 1) & nm;
        nh[pos] = lit;
    }
    free(ghash);
    ghash = nh;
    ghash_mask = nm;
}

static uint32_t aig_and(uint32_t a, uint32_t b) {
    if (a > b) { uint32_t t = a; a = b; b = t; }
    if (a == 0) return 0;
    if (a == 1) return b;
    if (a == b) return a;
    if ((a ^ b) == 1) return 0;
    uint64_t key = ((uint64_t)a << 32) | b;
    uint64_t h = key * 0x9E3779B97F4A7C15ull;
    uint32_t pos = (uint32_t)(h >> 32) & ghash_mask;
    while (ghash[pos]) {
        Gate g = gnodes.d[ghash[pos] >> 1];
        if (g.a == a && g.b == b) return ghash[pos];
        pos = (pos + 1) & ghash_mask;
    }
    Gate g = {a, b};
    vpush(gnodes, g);
    uint32_t lit = 2u * (uint32_t)(gnodes.n - 1);
    ghash[pos] = lit;
    if (++ghash_used * 2 > (int)ghash_mask) ghash_grow();
    return lit;
}

static uint32_t aig_or(uint32_t a, uint32_t b) {
    return aig_and(a ^ 1, b ^ 1) ^ 1;
}
static uint32_t aig_xor(uint32_t a, uint32_t b) {
    uint32_t t1 = aig_and(a, b ^ 1);
    uint32_t t2 = aig_and(a ^ 1, b);
    return aig_or(t1, t2);
}
static uint32_t aig_mux(uint32_t c, uint32_t t, uint32_t e) {
    uint32_t t1 = aig_and(c, t);
    uint32_t t2 = aig_and(c ^ 1, e);
    return aig_or(t1, t2);
}

/* ---------------- words ---------------- */
typedef struct { uint32_t *lit; int w; } Word;

static Word **frames;              /* frames[t][nid] */
static uint8_t **havew;
static int nframes_alloc;

static void ensure_frame(int t) {
    if (t < nframes_alloc) return;
    int nn = t + 8;
    frames = realloc(frames, sizeof(Word *) * (size_t)nn);
    havew = realloc(havew, sizeof(uint8_t *) * (size_t)nn);
    for (int i = nframes_alloc; i < nn; i++) {
        frames[i] = calloc((size_t)max_id + 1, sizeof(Word));
        havew[i] = calloc((size_t)max_id + 1, 1);
    }
    nframes_alloc = nn;
}

static Word wref(long long r, int t) {
    long long nid = r < 0 ? -r : r;
    Word w = frames[t][nid];
    if (r < 0) {
        Word o;
        o.w = w.w;
        o.lit = malloc(sizeof(uint32_t) * (size_t)w.w);
        for (int i = 0; i < w.w; i++) o.lit[i] = w.lit[i] ^ 1;
        return o;                      /* caller-owned copy */
    }
    return w;                          /* shared, do not free */
}

static Word walloc(int w) {
    Word o;
    o.w = w;
    o.lit = malloc(sizeof(uint32_t) * (size_t)(w ? w : 1));
    return o;
}

static Word wadd(Word a, Word b, uint32_t cin) {
    int w = a.w < b.w ? a.w : b.w;
    Word o = walloc(w);
    o.w = w;
    uint32_t c = cin;
    for (int i = 0; i < w; i++) {
        uint32_t x = a.lit[i], y = b.lit[i];
        uint32_t xy = aig_xor(x, y);
        uint32_t s = aig_xor(xy, c);
        uint32_t t1 = aig_and(x, y);
        uint32_t t2 = aig_and(c, xy);
        c = aig_or(t1, t2);
        o.lit[i] = s;
    }
    return o;
}

static Word wnotw(Word a) {
    Word o = walloc(a.w);
    for (int i = 0; i < a.w; i++) o.lit[i] = a.lit[i] ^ 1;
    return o;
}

static Word wconstw(int w, int v01) {
    Word o = walloc(w);
    for (int i = 0; i < w; i++) o.lit[i] = 0;
    if (v01 && w) o.lit[0] = 1;
    return o;
}

static Word wsub(Word a, Word b) {
    Word nb = wnotw(b);
    Word o = wadd(a, nb, 1);
    free(nb.lit);
    return o;
}

static Word wneg(Word a) {
    Word na = wnotw(a);
    Word z = wconstw(a.w, 0);
    Word o = wadd(na, z, 1);
    free(na.lit); free(z.lit);
    return o;
}

static uint32_t weq(Word a, Word b) {
    uint32_t ne = 0;
    for (int i = 0; i < a.w; i++)
        ne = aig_or(ne, aig_xor(a.lit[i], b.lit[i]));
    return ne ^ 1;
}

static uint32_t wult(Word a, Word b) {
    uint32_t lt = 0;
    for (int i = 0; i < a.w; i++) {
        uint32_t same = aig_xor(a.lit[i], b.lit[i]) ^ 1;
        uint32_t t1 = aig_and(a.lit[i] ^ 1, b.lit[i]);
        uint32_t t2 = aig_and(same, lt);
        lt = aig_or(t1, t2);
    }
    return lt;
}

static uint32_t wslt(Word a, Word b) {
    Word fa = walloc(a.w), fb = walloc(b.w);
    memcpy(fa.lit, a.lit, sizeof(uint32_t) * (size_t)a.w);
    memcpy(fb.lit, b.lit, sizeof(uint32_t) * (size_t)b.w);
    fa.lit[a.w - 1] ^= 1;
    fb.lit[b.w - 1] ^= 1;
    uint32_t r = wult(fa, fb);
    free(fa.lit); free(fb.lit);
    return r;
}

static Word wmuxw(uint32_t c, Word t, Word e) {
    Word o = walloc(t.w);
    for (int i = 0; i < t.w; i++)
        o.lit[i] = aig_mux(c, t.lit[i], e.lit[i]);
    return o;
}

static Word wmul(Word a, Word b) {
    int w = a.w;
    Word acc = wconstw(w, 0);
    for (int i = 0; i < w; i++) {
        uint32_t bi = b.lit[i];
        if (bi == 0) continue;
        Word part = walloc(w);
        for (int j = 0; j < i; j++) part.lit[j] = 0;
        for (int j = 0; j < w - i; j++) part.lit[i + j] = a.lit[j];
        if (bi != 1)
            for (int j = 0; j < w; j++)
                part.lit[j] = aig_and(bi, part.lit[j]);
        Word na = wadd(acc, part, 0);
        free(acc.lit); free(part.lit);
        acc = na;
    }
    return acc;
}

static void wudiv(Word a, Word b, Word *q_out, Word *r_out) {
    int w = a.w;
    Word bx = walloc(w + 1);
    memcpy(bx.lit, b.lit, sizeof(uint32_t) * (size_t)w);
    bx.lit[w] = 0;
    Word rem = walloc(w + 1);
    for (int i = 0; i <= w; i++) rem.lit[i] = 0;
    Word q = walloc(w);
    for (int i = w - 1; i >= 0; i--) {
        Word nrem = walloc(w + 1);
        nrem.lit[0] = a.lit[i];
        for (int j = 0; j < w; j++) nrem.lit[j + 1] = rem.lit[j];
        free(rem.lit);
        rem = nrem;
        uint32_t ge = wult(rem, bx) ^ 1;
        Word sub = wsub(rem, bx);
        Word mixed = wmuxw(ge, sub, rem);
        free(sub.lit); free(rem.lit);
        rem = mixed;
        q.lit[i] = ge;
    }
    free(bx.lit);
    Word r = walloc(w);
    memcpy(r.lit, rem.lit, sizeof(uint32_t) * (size_t)w);
    free(rem.lit);
    *q_out = q;
    *r_out = r;
}

static Word wshift(Word a, Word b, int kind) { /* 0 sll 1 srl 2 sra */
    int w = a.w;
    uint32_t fill = kind == 2 ? a.lit[w - 1] : 0;
    Word out = walloc(w);
    memcpy(out.lit, a.lit, sizeof(uint32_t) * (size_t)w);
    /* mirror: for s in range(w.bit_length()) */
    int wbits = 0;
    for (int x = w; x; x >>= 1) wbits++;
    for (int s = 0; s < wbits; s++) {
        if (s >= b.w) break;
        int sh = 1 << s;
        Word shifted = walloc(w);
        if (kind == 0) {
            int z = sh < w ? sh : w;
            for (int j = 0; j < z; j++) shifted.lit[j] = 0;
            for (int j = 0; j < w - z; j++) shifted.lit[z + j] = out.lit[j];
        } else {
            int z = sh < w ? sh : w;
            for (int j = 0; j < w - z; j++) shifted.lit[j] = out.lit[j + z];
            for (int j = w - z; j < w; j++) shifted.lit[j] = fill;
        }
        Word nx = wmuxw(b.lit[s], shifted, out);
        free(shifted.lit); free(out.lit);
        out = nx;
    }
    uint32_t big = 0;
    for (int j = 0; j < b.w; j++)
        if ((1LL << j) >= w) big = aig_or(big, b.lit[j]);
    Word res = walloc(w);
    for (int i = 0; i < w; i++) res.lit[i] = aig_mux(big, fill, out.lit[i]);
    free(out.lit);
    return res;
}


/* ---------------- array terms (mirrors the Blaster's array layer) --------
 * Hash-consed terms; interning order, select order, axiom order and every
 * weq/wmux argument order mirror the Python reference call for call, so
 * AIG node numbering — and with it the whole trajectory — is identical. */
enum { AT_BASE, AT_CONST, AT_WRITE, AT_ITE };

typedef struct {
    int kind;
    int bnid, bt;          /* AT_BASE                          */
    uint32_t *cw;          /* AT_CONST: element word (ew lits) */
    int sub, sub2;         /* AT_WRITE: sub | AT_ITE: sub,sub2 */
    uint32_t cond;         /* AT_ITE                           */
    uint32_t *idx, *val;   /* AT_WRITE (iw, ew lits)           */
    int iw, ew;
} AT;

static VEC(AT) aterms;               /* aid 1..n; slot 0 unused */
typedef struct { uint32_t *idx; uint32_t *w; } Sel;
typedef VEC(Sel) SelVec;
typedef struct { uint32_t e; int aA, aB; } EqRec;
typedef VEC(EqRec) EqVec;
static SelVec *base_sels;            /* per aid                 */
static EqVec *base_eqs;              /* per aid                 */
static VEC(uint32_t) axioms_v;
static IVec *bas_memo;               /* per aid: sorted base ids */
static uint8_t *bas_have;
typedef VEC(uint32_t *) WixVec;
static WixVec *wix_memo;             /* per aid: write index words */
static uint8_t *wix_have;
static int aterms_cap2;

static uint64_t mix64(uint64_t h, uint64_t x) {
    h ^= x + 0x9E3779B97F4A7C15ull + (h << 6) + (h >> 2);
    return h;
}

static uint64_t at_hash(const AT *a) {
    uint64_t h = (uint64_t)a->kind;
    if (a->kind == AT_BASE) { h = mix64(h, (uint64_t)a->bnid);
                              h = mix64(h, (uint64_t)a->bt); }
    else if (a->kind == AT_CONST)
        for (int i = 0; i < a->ew; i++) h = mix64(h, a->cw[i]);
    else if (a->kind == AT_WRITE) {
        h = mix64(h, (uint64_t)a->sub);
        for (int i = 0; i < a->iw; i++) h = mix64(h, a->idx[i]);
        for (int i = 0; i < a->ew; i++) h = mix64(h, a->val[i]);
    } else {
        h = mix64(h, a->cond);
        h = mix64(h, (uint64_t)a->sub);
        h = mix64(h, (uint64_t)a->sub2);
    }
    return h;
}

static int at_equal(const AT *a, const AT *b) {
    if (a->kind != b->kind || a->iw != b->iw || a->ew != b->ew) return 0;
    switch (a->kind) {
    case AT_BASE: return a->bnid == b->bnid && a->bt == b->bt;
    case AT_CONST:
        return !memcmp(a->cw, b->cw, sizeof(uint32_t) * (size_t)a->ew);
    case AT_WRITE:
        return a->sub == b->sub
            && !memcmp(a->idx, b->idx, sizeof(uint32_t) * (size_t)a->iw)
            && !memcmp(a->val, b->val, sizeof(uint32_t) * (size_t)a->ew);
    default:
        return a->cond == b->cond && a->sub == b->sub && a->sub2 == b->sub2;
    }
}

static struct { int *aid; uint32_t mask, used; } athash;

static void at_side_grow(void) {
    int n = aterms.n + 1;
    if (n <= aterms_cap2) return;
    int nc = aterms_cap2 ? aterms_cap2 * 2 : 64;
    while (nc < n) nc *= 2;
    base_sels = realloc(base_sels, sizeof(SelVec) * (size_t)nc);
    base_eqs = realloc(base_eqs, sizeof(EqVec) * (size_t)nc);
    bas_memo = realloc(bas_memo, sizeof(IVec) * (size_t)nc);
    bas_have = realloc(bas_have, (size_t)nc);
    wix_memo = realloc(wix_memo, sizeof(WixVec) * (size_t)nc);
    wix_have = realloc(wix_have, (size_t)nc);
    memset(base_sels + aterms_cap2, 0,
           sizeof(SelVec) * (size_t)(nc - aterms_cap2));
    memset(base_eqs + aterms_cap2, 0,
           sizeof(EqVec) * (size_t)(nc - aterms_cap2));
    memset(bas_memo + aterms_cap2, 0,
           sizeof(IVec) * (size_t)(nc - aterms_cap2));
    memset(bas_have + aterms_cap2, 0, (size_t)(nc - aterms_cap2));
    memset(wix_memo + aterms_cap2, 0,
           sizeof(WixVec) * (size_t)(nc - aterms_cap2));
    memset(wix_have + aterms_cap2, 0, (size_t)(nc - aterms_cap2));
    aterms_cap2 = nc;
}

static int at_intern(AT a) {
    if (!athash.aid) {
        athash.mask = (1 << 12) - 1;
        athash.aid = calloc((size_t)athash.mask + 1, sizeof(int));
        AT dummy;
        memset(&dummy, 0, sizeof dummy);
        vpush(aterms, dummy);           /* slot 0 unused */
        at_side_grow();
    }
    uint64_t h = at_hash(&a);
    uint32_t pos = (uint32_t)(h >> 32) & athash.mask;
    while (athash.aid[pos]) {
        if (at_equal(&aterms.d[athash.aid[pos]], &a))
            return athash.aid[pos];
        pos = (pos + 1) & athash.mask;
    }
    vpush(aterms, a);
    int aid = aterms.n - 1;
    athash.aid[pos] = aid;
    at_side_grow();
    if (++athash.used * 2 > athash.mask) {
        uint32_t nm = athash.mask * 2 + 1;
        int *nh = calloc((size_t)nm + 1, sizeof(int));
        for (uint32_t i = 0; i <= athash.mask; i++) {
            int id = athash.aid[i];
            if (!id) continue;
            uint64_t hh = at_hash(&aterms.d[id]);
            uint32_t p = (uint32_t)(hh >> 32) & nm;
            while (nh[p]) p = (p + 1) & nm;
            nh[p] = id;
        }
        free(athash.aid);
        athash.aid = nh;
        athash.mask = nm;
    }
    return aid;
}

/* select cache: (aid, idx literal vector) -> element word */
typedef struct { int aid; uint32_t *idx; uint32_t *w; } SelKey;
static struct { SelKey *e; uint32_t mask, used; } selh;

static uint32_t *sel_cache_get(int aid, const uint32_t *idx, int iw) {
    if (!selh.e) return NULL;
    uint64_t h = (uint64_t)aid;
    for (int i = 0; i < iw; i++) h = mix64(h, idx[i]);
    uint32_t pos = (uint32_t)(h >> 32) & selh.mask;
    while (selh.e[pos].w) {
        if (selh.e[pos].aid == aid
            && !memcmp(selh.e[pos].idx, idx,
                       sizeof(uint32_t) * (size_t)iw))
            return selh.e[pos].w;
        pos = (pos + 1) & selh.mask;
    }
    return NULL;
}

static void sel_cache_put(int aid, const uint32_t *idx, int iw,
                          uint32_t *w) {
    if (!selh.e) {
        selh.mask = (1 << 12) - 1;
        selh.e = calloc((size_t)selh.mask + 1, sizeof(SelKey));
    }
    uint64_t h = (uint64_t)aid;
    for (int i = 0; i < iw; i++) h = mix64(h, idx[i]);
    uint32_t pos = (uint32_t)(h >> 32) & selh.mask;
    while (selh.e[pos].w) {
        if (selh.e[pos].aid == aid
            && !memcmp(selh.e[pos].idx, idx,
                       sizeof(uint32_t) * (size_t)iw)) {
            selh.e[pos].w = w;          /* refresh (base pre-cache) */
            return;
        }
        pos = (pos + 1) & selh.mask;
    }
    uint32_t *ic = malloc(sizeof(uint32_t) * (size_t)(iw ? iw : 1));
    memcpy(ic, idx, sizeof(uint32_t) * (size_t)iw);
    selh.e[pos].aid = aid;
    selh.e[pos].idx = ic;
    selh.e[pos].w = w;
    if (++selh.used * 2 > selh.mask) {
        uint32_t nm = selh.mask * 2 + 1;
        SelKey *ne = calloc((size_t)nm + 1, sizeof(SelKey));
        for (uint32_t i = 0; i <= selh.mask; i++) {
            if (!selh.e[i].w) continue;
            const AT *at = &aterms.d[selh.e[i].aid];
            uint64_t hh = (uint64_t)selh.e[i].aid;
            for (int j = 0; j < at->iw; j++)
                hh = mix64(hh, selh.e[i].idx[j]);
            uint32_t p = (uint32_t)(hh >> 32) & nm;
            while (ne[p].w) p = (p + 1) & nm;
            ne[p] = selh.e[i];
        }
        free(selh.e);
        selh.e = ne;
        selh.mask = nm;
    }
}

/* eq cache: unordered (aA,aB) -> literal e; eq_done: (e, idx) set */
typedef struct { int aA, aB; uint32_t e; uint8_t used; } EqKey;
static struct { EqKey *e; uint32_t mask, used; } eqh;

typedef struct { uint32_t e; uint32_t *idx; int iw; } DoneKey;
static struct { DoneKey *e; uint32_t mask, used; } doneh;

static int eq_done_check_add(uint32_t e, const uint32_t *idx, int iw) {
    if (!doneh.e) {
        doneh.mask = (1 << 12) - 1;
        doneh.e = calloc((size_t)doneh.mask + 1, sizeof(DoneKey));
    }
    uint64_t h = e;
    for (int i = 0; i < iw; i++) h = mix64(h, idx[i]);
    uint32_t pos = (uint32_t)(h >> 32) & doneh.mask;
    while (doneh.e[pos].idx) {
        if (doneh.e[pos].e == e && doneh.e[pos].iw == iw
            && !memcmp(doneh.e[pos].idx, idx,
                       sizeof(uint32_t) * (size_t)iw))
            return 1;
        pos = (pos + 1) & doneh.mask;
    }
    uint32_t *ic = malloc(sizeof(uint32_t) * (size_t)(iw ? iw : 1));
    memcpy(ic, idx, sizeof(uint32_t) * (size_t)iw);
    doneh.e[pos].e = e;
    doneh.e[pos].idx = ic;
    doneh.e[pos].iw = iw;
    if (++doneh.used * 2 > doneh.mask) {
        uint32_t nm = doneh.mask * 2 + 1;
        DoneKey *ne = calloc((size_t)nm + 1, sizeof(DoneKey));
        for (uint32_t i = 0; i <= doneh.mask; i++) {
            if (!doneh.e[i].idx) continue;
            uint64_t hh = doneh.e[i].e;
            for (int j = 0; j < doneh.e[i].iw; j++)
                hh = mix64(hh, doneh.e[i].idx[j]);
            uint32_t p = (uint32_t)(hh >> 32) & nm;
            while (ne[p].idx) p = (p + 1) & nm;
            ne[p] = doneh.e[i];
        }
        free(doneh.e);
        doneh.e = ne;
        doneh.mask = nm;
    }
    return 0;
}

/* base ids under a term, sorted ascending (mirrors _bases_of)        */
static void bases_of(int aid, IVec *out);

static void ivec_merge_sorted(IVec *dst, const IVec *a, const IVec *b) {
    int i = 0, j = 0;
    dst->n = 0;
    while (i < a->n || j < b->n) {
        int v;
        if (j >= b->n || (i < a->n && a->d[i] <= b->d[j])) {
            v = a->d[i++];
            if (j < b->n && b->d[j] == v) j++;
        } else v = b->d[j++];
        if (dst->n == 0 || dst->d[dst->n - 1] != v) vpush(*dst, v);
    }
}

static void bases_of(int aid, IVec *out) {
    if (!bas_have[aid]) {
        IVec r = {0};
        const AT *a = &aterms.d[aid];
        if (a->kind == AT_BASE) vpush(r, aid);
        else if (a->kind == AT_WRITE) {
            IVec s = {0};
            bases_of(a->sub, &s);
            r = s;
        } else if (a->kind == AT_ITE) {
            IVec x = {0}, y = {0};
            bases_of(a->sub, &x);
            bases_of(a->sub2, &y);
            ivec_merge_sorted(&r, &x, &y);
            free(x.d); free(y.d);
        }
        bas_memo[aid] = r;
        bas_have[aid] = 1;
    }
    out->n = 0;
    for (int i = 0; i < bas_memo[aid].n; i++) vpush(*out, bas_memo[aid].d[i]);
}

/* write index words under a term, deduplicated (mirrors _write_indices) */
static void wix_of(int aid, WixVec *out, int iw);

static void wix_add_unique(WixVec *v, uint32_t *idx, int iw) {
    for (int i = 0; i < v->n; i++)
        if (!memcmp(v->d[i], idx, sizeof(uint32_t) * (size_t)iw)) return;
    vpush(*v, idx);
}

static void wix_of(int aid, WixVec *out, int iw) {
    if (!wix_have[aid]) {
        WixVec r = {0};
        const AT *a = &aterms.d[aid];
        if (a->kind == AT_WRITE) {
            WixVec s = {0};
            wix_of(a->sub, &s, iw);
            for (int i = 0; i < s.n; i++) wix_add_unique(&r, s.d[i], iw);
            free(s.d);
            wix_add_unique(&r, a->idx, iw);
        } else if (a->kind == AT_ITE) {
            WixVec x = {0}, y = {0};
            wix_of(a->sub, &x, iw);
            wix_of(a->sub2, &y, iw);
            for (int i = 0; i < x.n; i++) wix_add_unique(&r, x.d[i], iw);
            for (int i = 0; i < y.n; i++) wix_add_unique(&r, y.d[i], iw);
            free(x.d); free(y.d);
        }
        wix_memo[aid] = r;
        wix_have[aid] = 1;
    }
    for (int i = 0; i < wix_memo[aid].n; i++)
        wix_add_unique(out, wix_memo[aid].d[i], iw);
}

static int wixcmp_iw;
static int wixcmp(const void *a, const void *b) {
    const uint32_t *x = *(uint32_t *const *)a;
    const uint32_t *y = *(uint32_t *const *)b;
    for (int i = 0; i < wixcmp_iw; i++) {
        if (x[i] < y[i]) return -1;
        if (x[i] > y[i]) return 1;
    }
    return 0;
}

static uint32_t *at_select(int aid, const uint32_t *idx);

static void inst_eq(uint32_t e, int aA, int aB, const uint32_t *idx,
                    int iw, int ew) {
    if (eq_done_check_add(e, idx, iw)) return;
    uint32_t *ra = at_select(aA, idx);
    uint32_t *rb = at_select(aB, idx);
    Word wa = {ra, ew}, wb = {rb, ew};
    uint32_t ag = weq(wa, wb);
    vpush(axioms_v, aig_or(e ^ 1, ag));
}

static uint32_t *at_select(int aid, const uint32_t *idx) {
    const AT *a = &aterms.d[aid];
    int iw = a->iw, ew = a->ew;
    uint32_t *hit_w = sel_cache_get(aid, idx, iw);
    if (hit_w) return hit_w;
    uint32_t *w;
    if (a->kind == AT_CONST) {
        w = malloc(sizeof(uint32_t) * (size_t)(ew ? ew : 1));
        memcpy(w, a->cw, sizeof(uint32_t) * (size_t)ew);
    } else if (a->kind == AT_WRITE) {
        Word wi = {(uint32_t *)idx, iw}, wj = {a->idx, iw};
        uint32_t hit = weq(wi, wj);
        uint32_t *sub = at_select(a->sub, idx);
        w = malloc(sizeof(uint32_t) * (size_t)(ew ? ew : 1));
        for (int i = 0; i < ew; i++)
            w[i] = aig_mux(hit, a->val[i], sub[i]);
    } else if (a->kind == AT_ITE) {
        uint32_t *x = at_select(a->sub, idx);
        uint32_t *y = at_select(a->sub2, idx);
        w = malloc(sizeof(uint32_t) * (size_t)(ew ? ew : 1));
        for (int i = 0; i < ew; i++)
            w[i] = aig_mux(a->cond, x[i], y[i]);
    } else {                             /* a symbolic base */
        w = malloc(sizeof(uint32_t) * (size_t)(ew ? ew : 1));
        for (int i = 0; i < ew; i++) w[i] = aig_var();
        sel_cache_put(aid, idx, iw, w);  /* before axioms: reentry-safe */
        int nprior = base_sels[aid].n;
        for (int s = 0; s < nprior; s++) {
            Sel *p = &base_sels[aid].d[s];
            Word wi = {(uint32_t *)idx, iw}, wp = {p->idx, iw};
            uint32_t same = weq(wi, wp);
            Word ww = {w, ew}, pw = {p->w, ew};
            uint32_t agree = weq(ww, pw);
            vpush(axioms_v, aig_or(same ^ 1, agree));
        }
        Sel ns;
        ns.idx = malloc(sizeof(uint32_t) * (size_t)(iw ? iw : 1));
        memcpy(ns.idx, idx, sizeof(uint32_t) * (size_t)iw);
        ns.w = w;
        vpush(base_sels[aid], ns);
        int neq = base_eqs[aid].n;
        for (int r = 0; r < neq; r++) {
            EqRec rec = base_eqs[aid].d[r];
            inst_eq(rec.e, rec.aA, rec.aB, idx, iw, ew);
        }
        return w;
    }
    sel_cache_put(aid, idx, iw, w);
    return w;
}

static uint32_t at_eq(int aA, int aB, int iw, int ew) {
    if (aA == aB) return 1;
    int lo = aA < aB ? aA : aB, hi = aA < aB ? aB : aA;
    if (!eqh.e) {
        eqh.mask = (1 << 10) - 1;
        eqh.e = calloc((size_t)eqh.mask + 1, sizeof(EqKey));
    }
    uint64_t h = mix64((uint64_t)lo, (uint64_t)hi);
    uint32_t pos = (uint32_t)(h >> 32) & eqh.mask;
    while (eqh.e[pos].used) {
        if (eqh.e[pos].aA == lo && eqh.e[pos].aB == hi)
            return eqh.e[pos].e;
        pos = (pos + 1) & eqh.mask;
    }
    uint32_t e = aig_var();
    eqh.e[pos].aA = lo;
    eqh.e[pos].aB = hi;
    eqh.e[pos].e = e;
    eqh.e[pos].used = 1;
    if (++eqh.used * 2 > eqh.mask) {
        uint32_t nm = eqh.mask * 2 + 1;
        EqKey *ne = calloc((size_t)nm + 1, sizeof(EqKey));
        for (uint32_t i = 0; i <= eqh.mask; i++) {
            if (!eqh.e[i].used) continue;
            uint64_t hh = mix64((uint64_t)eqh.e[i].aA,
                                (uint64_t)eqh.e[i].aB);
            uint32_t p = (uint32_t)(hh >> 32) & nm;
            while (ne[p].used) p = (p + 1) & nm;
            ne[p] = eqh.e[i];
        }
        free(eqh.e);
        eqh.e = ne;
        eqh.mask = nm;
    }
    IVec ba = {0}, bb = {0}, bu = {0};
    bases_of(aA, &ba);
    bases_of(aB, &bb);
    ivec_merge_sorted(&bu, &ba, &bb);
    free(ba.d); free(bb.d);
    for (int i = 0; i < bu.n; i++) {
        int b = bu.d[i];
        EqRec rec = {e, aA, aB};
        vpush(base_eqs[b], rec);
        int nprior = base_sels[b].n;
        for (int s = 0; s < nprior; s++)
            inst_eq(e, aA, aB, base_sels[b].d[s].idx, iw, ew);
    }
    free(bu.d);
    WixVec wu = {0};
    wix_of(aA, &wu, iw);
    wix_of(aB, &wu, iw);
    wixcmp_iw = iw;
    qsort(wu.d, (size_t)wu.n, sizeof(uint32_t *), wixcmp);
    for (int i = 0; i < wu.n; i++)
        inst_eq(e, aA, aB, wu.d[i], iw, ew);
    free(wu.d);
    uint32_t *wit = malloc(sizeof(uint32_t) * (size_t)(iw ? iw : 1));
    for (int i = 0; i < iw; i++) wit[i] = aig_var();
    uint32_t *ra = at_select(aA, wit);
    uint32_t *rb = at_select(aB, wit);
    Word wa = {ra, ew}, wb = {rb, ew};
    vpush(axioms_v, aig_or(e, weq(wa, wb) ^ 1));
    free(wit);
    return e;
}

/* demand-driven word() — mirrors Blaster.word()'s explicit stack     */
typedef struct { int nid, t; } Key;
static VEC(Key) wstack;

static int deps_of(int nid, int t, Key *out) {
    Node *nd = &nodes[nid];
    switch (nd->op) {
    case OP_CONST: case OP_INPUT: return 0;
    case OP_STATE: {
        long long r;
        if (t == 0) { if (!has_init[nid]) return 0; r = init_ref[nid]; }
        else { if (!has_next[nid]) return 0; r = next_ref[nid]; }
        out[0].nid = (int)(r < 0 ? -r : r);
        out[0].t = t == 0 ? 0 : t - 1;
        return 1;
    }
    case OP_SLICE: case OP_UEXT: case OP_SEXT:
        out[0].nid = (int)(nd->a[0] < 0 ? -nd->a[0] : nd->a[0]);
        out[0].t = t;
        return 1;
    default: {
        int n = 0;
        for (int i = 0; i < nd->na; i++) {
            out[n].nid = (int)(nd->a[i] < 0 ? -nd->a[i] : nd->a[i]);
            out[n].t = t;
            n++;
        }
        return n;
    }
    }
}

/* an array-typed (node, frame) stores its term id in the Word marker */
static Word amarker(int aid) {
    Word m;
    m.lit = NULL;
    m.w = -aid;
    return m;
}

static int aref(long long r, int t) {
    if (r < 0) partial_exit("negated array reference");
    return -frames[t][r].w;
}

static Word compute_word(int nid, int t) {
    Node *nd = &nodes[nid];
    int w = nd->width;
    if (nd->op == OP_READ) {
        int aid = aref(nd->a[0], t);
        Word idx = wref(nd->a[1], t);
        uint32_t *sel = at_select(aid, idx.lit);
        int ew = aterms.d[aid].ew;
        Word o = walloc(ew);
        memcpy(o.lit, sel, sizeof(uint32_t) * (size_t)ew);
        if (nd->a[1] < 0) free(idx.lit);
        return o;
    }
    if (nd->op == OP_WRITE) {
        AT a;
        memset(&a, 0, sizeof a);
        a.kind = AT_WRITE;
        a.iw = nd->aiw;
        a.ew = nd->aew;
        a.sub = aref(nd->a[0], t);
        Word idx = wref(nd->a[1], t), val = wref(nd->a[2], t);
        a.idx = malloc(sizeof(uint32_t) * (size_t)(a.iw ? a.iw : 1));
        memcpy(a.idx, idx.lit, sizeof(uint32_t) * (size_t)a.iw);
        a.val = malloc(sizeof(uint32_t) * (size_t)(a.ew ? a.ew : 1));
        memcpy(a.val, val.lit, sizeof(uint32_t) * (size_t)a.ew);
        if (nd->a[1] < 0) free(idx.lit);
        if (nd->a[2] < 0) free(val.lit);
        return amarker(at_intern(a));
    }
    if ((nd->op == OP_EQ || nd->op == OP_NEQ)
        && nodes[nd->a[0] < 0 ? -nd->a[0] : nd->a[0]].is_arr) {
        Node *an = &nodes[nd->a[0] < 0 ? -nd->a[0] : nd->a[0]];
        uint32_t e = at_eq(aref(nd->a[0], t), aref(nd->a[1], t),
                           an->aiw, an->aew);
        Word o = walloc(1);
        o.lit[0] = nd->op == OP_EQ ? e : e ^ 1;
        return o;
    }
    switch (nd->op) {
    case OP_CONST: {
        Word o = walloc(w);
        for (int i = 0; i < w; i++) o.lit[i] = nd->cbits[i];
        return o;
    }
    case OP_INPUT: {
        if (nd->is_arr) {
            AT a;
            memset(&a, 0, sizeof a);
            a.kind = AT_BASE;
            a.bnid = nid;
            a.bt = t;
            a.iw = nd->aiw;
            a.ew = nd->aew;
            return amarker(at_intern(a));
        }
        Word o = walloc(w);
        for (int i = 0; i < w; i++) o.lit[i] = aig_var();
        return o;
    }
    case OP_STATE: {
        int have = t == 0 ? has_init[nid] : has_next[nid];
        if (nd->is_arr) {
            if (!have) {
                AT a;
                memset(&a, 0, sizeof a);
                a.kind = AT_BASE;
                a.bnid = nid;
                a.bt = t;
                a.iw = nd->aiw;
                a.ew = nd->aew;
                return amarker(at_intern(a));
            }
            long long r = t == 0 ? init_ref[nid] : next_ref[nid];
            long long rn = r < 0 ? -r : r;
            int rt = t == 0 ? 0 : t - 1;
            if (nodes[rn].is_arr)
                return amarker(aref(r, rt));
            /* a bitvec init broadcasts into the constant array */
            Word v = wref(r, rt);
            AT a;
            memset(&a, 0, sizeof a);
            a.kind = AT_CONST;
            a.iw = nd->aiw;
            a.ew = nd->aew;
            a.cw = malloc(sizeof(uint32_t) * (size_t)(a.ew ? a.ew : 1));
            memcpy(a.cw, v.lit, sizeof(uint32_t) * (size_t)a.ew);
            if (r < 0) free(v.lit);
            return amarker(at_intern(a));
        }
        if (!have) {
            Word o = walloc(w);
            for (int i = 0; i < w; i++) o.lit[i] = aig_var();
            return o;
        }
        long long r = t == 0 ? init_ref[nid] : next_ref[nid];
        Word src = wref(r, t == 0 ? 0 : t - 1);
        Word o = walloc(w);
        memcpy(o.lit, src.lit, sizeof(uint32_t) * (size_t)w);
        if (r < 0) free(src.lit);
        return o;
    }
    case OP_ITE: {
        if (nd->is_arr) {
            Word c = wref(nd->a[0], t);
            uint32_t cl = c.lit[0];
            if (nd->a[0] < 0) free(c.lit);
            int x = aref(nd->a[1], t), y = aref(nd->a[2], t);
            if (cl == 1 || x == y) return amarker(x);
            if (cl == 0) return amarker(y);
            AT a;
            memset(&a, 0, sizeof a);
            a.kind = AT_ITE;
            a.cond = cl;
            a.sub = x;
            a.sub2 = y;
            a.iw = nd->aiw;
            a.ew = nd->aew;
            return amarker(at_intern(a));
        }
        Word c = wref(nd->a[0], t), x = wref(nd->a[1], t),
             e = wref(nd->a[2], t);
        Word o = wmuxw(c.lit[0], x, e);
        if (nd->a[0] < 0) free(c.lit);
        if (nd->a[1] < 0) free(x.lit);
        if (nd->a[2] < 0) free(e.lit);
        return o;
    }
    case OP_SLICE: {
        Word x = wref(nd->a[0], t);
        int hi = (int)nd->a[1], lo = (int)nd->a[2];
        Word o = walloc(hi - lo + 1);
        for (int i = 0; i < o.w; i++) o.lit[i] = x.lit[lo + i];
        if (nd->a[0] < 0) free(x.lit);
        return o;
    }
    case OP_UEXT: case OP_SEXT: {
        Word x = wref(nd->a[0], t);
        Word o = walloc(w);
        for (int i = 0; i < x.w; i++) o.lit[i] = x.lit[i];
        uint32_t top = nd->op == OP_SEXT ? x.lit[x.w - 1] : 0;
        for (int i = x.w; i < w; i++) o.lit[i] = top;
        if (nd->a[0] < 0) free(x.lit);
        return o;
    }
    case OP_CONCAT: {
        Word hiw = wref(nd->a[0], t), low = wref(nd->a[1], t);
        Word o = walloc(w);
        for (int i = 0; i < low.w; i++) o.lit[i] = low.lit[i];
        for (int i = 0; i < hiw.w; i++) o.lit[low.w + i] = hiw.lit[i];
        if (nd->a[0] < 0) free(hiw.lit);
        if (nd->a[1] < 0) free(low.lit);
        return o;
    }
    default: break;
    }
    if (nd->op >= OP_NOT && nd->op <= OP_REDXOR) {
        Word x = wref(nd->a[0], t);
        Word o;
        switch (nd->op) {
        case OP_NOT: o = wnotw(x); break;
        case OP_NEG: o = wneg(x); break;
        case OP_INC: { Word one = wconstw(w, 1); o = wadd(x, one, 0);
                       free(one.lit); break; }
        case OP_DEC: { Word one = wconstw(w, 1); o = wsub(x, one);
                       free(one.lit); break; }
        default: {
            uint32_t acc = x.lit[0];
            for (int i = 1; i < x.w; i++)
                acc = nd->op == OP_REDAND ? aig_and(acc, x.lit[i])
                    : nd->op == OP_REDOR ? aig_or(acc, x.lit[i])
                    : aig_xor(acc, x.lit[i]);
            o = walloc(1);
            o.lit[0] = acc;
        }
        }
        if (nd->a[0] < 0) free(x.lit);
        return o;
    }
    Word x = wref(nd->a[0], t), y = wref(nd->a[1], t);
    Word o;
    uint32_t lit;
    switch (nd->op) {
    case OP_AND: case OP_OR: case OP_XOR:
    case OP_NAND: case OP_NOR: case OP_XNOR:
        o = walloc(w);
        for (int i = 0; i < w; i++) {
            uint32_t r =
                nd->op == OP_AND ? aig_and(x.lit[i], y.lit[i])
                : nd->op == OP_OR ? aig_or(x.lit[i], y.lit[i])
                : nd->op == OP_XOR ? aig_xor(x.lit[i], y.lit[i])
                : nd->op == OP_NAND ? aig_and(x.lit[i], y.lit[i]) ^ 1
                : nd->op == OP_NOR ? aig_or(x.lit[i], y.lit[i]) ^ 1
                : aig_xor(x.lit[i], y.lit[i]) ^ 1;
            o.lit[i] = r;
        }
        break;
    case OP_IMPLIES:
        o = walloc(1); o.lit[0] = aig_or(x.lit[0] ^ 1, y.lit[0]); break;
    case OP_IFF:
        o = walloc(1); o.lit[0] = aig_xor(x.lit[0], y.lit[0]) ^ 1; break;
    case OP_EQ: o = walloc(1); o.lit[0] = weq(x, y); break;
    case OP_NEQ: o = walloc(1); o.lit[0] = weq(x, y) ^ 1; break;
    case OP_ULT: case OP_ULTE: case OP_UGT: case OP_UGTE:
        lit = nd->op == OP_ULT ? wult(x, y)
            : nd->op == OP_ULTE ? wult(y, x) ^ 1
            : nd->op == OP_UGT ? wult(y, x)
            : wult(x, y) ^ 1;
        o = walloc(1); o.lit[0] = lit; break;
    case OP_SLT: case OP_SLTE: case OP_SGT: case OP_SGTE:
        lit = nd->op == OP_SLT ? wslt(x, y)
            : nd->op == OP_SLTE ? wslt(y, x) ^ 1
            : nd->op == OP_SGT ? wslt(y, x)
            : wslt(x, y) ^ 1;
        o = walloc(1); o.lit[0] = lit; break;
    case OP_ADD: o = wadd(x, y, 0); break;
    case OP_SUB: o = wsub(x, y); break;
    case OP_MUL: o = wmul(x, y); break;
    case OP_UDIV: { Word q, r; wudiv(x, y, &q, &r); free(r.lit); o = q;
                    break; }
    case OP_UREM: {
        Word q, r;
        wudiv(x, y, &q, &r);
        free(q.lit);
        uint32_t z = 0;
        for (int i = 0; i < y.w; i++) z = aig_or(z, y.lit[i]);
        o = wmuxw(z, r, x);
        free(r.lit);
        break;
    }
    case OP_SLL: o = wshift(x, y, 0); break;
    case OP_SRL: o = wshift(x, y, 1); break;
    case OP_SRA: o = wshift(x, y, 2); break;
    case OP_SDIV: case OP_SREM: case OP_SMOD: {
        /* magnitude circuits with sign correction; the call order
         * mirrors the Python reference exactly (node-creation parity) */
        Word nx = wneg(x);
        Word ax = wmuxw(x.lit[w - 1], nx, x);
        free(nx.lit);
        Word ny = wneg(y);
        Word ay = wmuxw(y.lit[w - 1], ny, y);
        free(ny.lit);
        Word q, rr;
        wudiv(ax, ay, &q, &rr);
        free(ax.lit);
        free(ay.lit);
        if (nd->op == OP_SDIV) {
            uint32_t diff = aig_xor(x.lit[w - 1], y.lit[w - 1]);
            Word nq = wneg(q);
            o = wmuxw(diff, nq, q);
            free(nq.lit);
        } else if (nd->op == OP_SREM) {
            Word nr = wneg(rr);
            o = wmuxw(x.lit[w - 1], nr, rr);
            free(nr.lit);
        } else {
            uint32_t nz = 0;
            for (int i = 0; i < rr.w; i++) nz = aig_or(nz, rr.lit[i]);
            Word nu = wneg(rr);
            Word r10 = wadd(nu, y, 0);
            Word r01 = wadd(rr, y, 0);
            Word pos = wmuxw(x.lit[w - 1], r10, rr);
            Word negb = wmuxw(x.lit[w - 1], nu, r01);
            Word resw = wmuxw(y.lit[w - 1], negb, pos);
            o = wmuxw(nz, resw, rr);
            free(nu.lit); free(r10.lit); free(r01.lit);
            free(pos.lit); free(negb.lit); free(resw.lit);
        }
        free(q.lit);
        free(rr.lit);
        break;
    }
    default: die("unsupported op"); o = walloc(0);
    }
    if (nd->a[0] < 0) free(x.lit);
    if (nd->a[1] < 0) free(y.lit);
    return o;
}

static Word *word_of(int nid, int t) {
    ensure_frame(t);
    if (havew[t][nid]) return &frames[t][nid];
    wstack.n = 0;
    {
        Key kk = {nid, t};
        vpush(wstack, kk);
        while (wstack.n) {
            Key k = wstack.d[wstack.n - 1];
            ensure_frame(k.t);
            if (havew[k.t][k.nid]) { wstack.n--; continue; }
            Key dep[3];
            int nd_ = deps_of(k.nid, k.t, dep);
            int missing = 0;
            for (int i = 0; i < nd_; i++) {
                ensure_frame(dep[i].t);
                if (!havew[dep[i].t][dep[i].nid]) {
                    vpush(wstack, dep[i]);
                    missing = 1;
                }
            }
            if (missing) continue;
            frames[k.t][k.nid] = compute_word(k.nid, k.t);
            havew[k.t][k.nid] = 1;
            wstack.n--;
        }
    }
    return &frames[t][nid];
}

static uint32_t bad_at(int t) {
    uint32_t lit = 0;
    for (int i = 0; i < bads_v.n; i++) {
        long long b = bads_v.d[i];
        Word *w = word_of((int)(b < 0 ? -b : b), t);
        uint32_t x = w->lit[0] ^ (b < 0 ? 1u : 0u);
        lit = aig_or(lit, x);
    }
    return lit;
}

static uint32_t constraint_at(int t) {
    uint32_t lit = 1;
    for (int i = 0; i < constraints_v.n; i++) {
        long long c = constraints_v.d[i];
        Word *w = word_of((int)(c < 0 ? -c : c), t);
        uint32_t x = w->lit[0] ^ (c < 0 ? 1u : 0u);
        lit = aig_and(lit, x);
    }
    return lit;
}

/* ---------------- CDCL (mirrors Solver) ---------------- */
#define ST_UNSAT 0
#define ST_SAT 1
#define ST_UNKNOWN 2

typedef struct { double negact; int var; } HeapItem;

static VEC(int *) clauses;
static VEC(int) clause_len;
static IVec *watches;              /* per literal */
static VEC(int8_t) assign_v;
static VEC(int) level_v, reason_v;
static VEC(int8_t) phase_v;
static VEC(double) act_v;
static VEC(HeapItem) heap_v;
static VEC(int) trail_v, lim_v;
static int qhead;
static double vinc = 1.0;
static long long conflicts;
static int solver_ok = 1;
static int watches_cap;

static int heap_less(HeapItem x, HeapItem y) {
    if (x.negact < y.negact) return 1;
    if (x.negact > y.negact) return 0;
    return x.var < y.var;
}

static void heap_push(HeapItem it) {
    vpush(heap_v, it);
    int pos = heap_v.n - 1;
    while (pos > 0) {
        int parent = (pos - 1) >> 1;
        if (heap_less(it, heap_v.d[parent])) {
            heap_v.d[pos] = heap_v.d[parent];
            pos = parent;
        } else break;
    }
    heap_v.d[pos] = it;
}

static HeapItem heap_pop(void) {
    HeapItem last = heap_v.d[--heap_v.n];
    if (heap_v.n) {
        HeapItem ret = heap_v.d[0];
        /* _siftup(heap, 0) with newitem = last */
        int pos = 0, endpos = heap_v.n;
        int childpos = 1;
        while (childpos < endpos) {
            int rightpos = childpos + 1;
            if (rightpos < endpos
                && !heap_less(heap_v.d[childpos], heap_v.d[rightpos]))
                childpos = rightpos;
            heap_v.d[pos] = heap_v.d[childpos];
            pos = childpos;
            childpos = 2 * pos + 1;
        }
        heap_v.d[pos] = last;
        /* _siftdown(heap, 0, pos) */
        while (pos > 0) {
            int parent = (pos - 1) >> 1;
            if (heap_less(last, heap_v.d[parent])) {
                heap_v.d[pos] = heap_v.d[parent];
                pos = parent;
            } else break;
        }
        heap_v.d[pos] = last;
        return ret;
    }
    return last;
}

static int new_var(void) {
    int v = assign_v.n;
    vpush(assign_v, -1);
    vpush(level_v, 0);
    vpush(reason_v, -1);
    vpush(phase_v, 0);
    vpush(act_v, 0.0);
    if (2 * v + 2 > watches_cap) {
        int nc = watches_cap ? watches_cap * 2 : 1024;
        while (nc < 2 * v + 2) nc *= 2;
        watches = realloc(watches, sizeof(*watches) * (size_t)nc);
        memset(watches + watches_cap, 0,
               sizeof(*watches) * (size_t)(nc - watches_cap));
        watches_cap = nc;
    }
    HeapItem it = {0.0, v};
    heap_push(it);
    return v;
}

static int value_of(int lit) {
    int8_t a = assign_v.d[lit >> 1];
    return a < 0 ? -1 : (a ^ (lit & 1));
}

static int enqueue(int lit, int reason) {
    int v = lit >> 1;
    int want = (lit & 1) ^ 1;
    if (assign_v.d[v] != -1) return assign_v.d[v] == want;
    assign_v.d[v] = (int8_t)want;
    level_v.d[v] = lim_v.n;
    reason_v.d[v] = reason;
    vpush(trail_v, lit);
    return 1;
}

static int cmp_int(const void *a, const void *b) {
    return *(const int *)a - *(const int *)b;
}

static int add_clause(int *lits, int n) {
    if (!solver_ok) return 0;
    qsort(lits, (size_t)n, sizeof(int), cmp_int);
    int m = 0;
    for (int i = 0; i < n; i++)
        if (m == 0 || lits[i] != lits[m - 1]) lits[m++] = lits[i];
    for (int i = 0; i < m; i++)
        for (int j = 0; j < m; j++)
            if (lits[i] == (lits[j] ^ 1)) return 1;      /* tautology */
    int k = 0;
    for (int i = 0; i < m; i++)
        if (value_of(lits[i]) != 0 || level_v.d[lits[i] >> 1] > 0)
            lits[k++] = lits[i];
    m = k;
    for (int i = 0; i < m; i++)
        if (value_of(lits[i]) == 1 && level_v.d[lits[i] >> 1] == 0)
            return 1;                                    /* satisfied */
    if (m == 0) { solver_ok = 0; return 0; }
    if (m == 1) {
        if (!enqueue(lits[0], -1)) solver_ok = 0;
        return solver_ok;
    }
    int *cl = malloc(sizeof(int) * (size_t)m);
    memcpy(cl, lits, sizeof(int) * (size_t)m);
    int ci = clauses.n;
    vpush(clauses, cl);
    vpush(clause_len, m);
    vpush(watches[cl[0] ^ 1], ci);
    vpush(watches[cl[1] ^ 1], ci);
    return 1;
}

static int propagate(void) {
    while (qhead < trail_v.n) {
        int p = trail_v.d[qhead++];
        int fl = p ^ 1;
        IVec *ws = &watches[p];
        int i = 0, j = 0, n = ws->n;
        while (i < n) {
            int ci = ws->d[i++];
            int *cl = clauses.d[ci];
            int len = clause_len.d[ci];
            if (cl[0] == fl) { cl[0] = cl[1]; cl[1] = fl; }
            int first = cl[0];
            if (value_of(first) == 1) { ws->d[j++] = ci; continue; }
            int moved = 0;
            for (int k = 2; k < len; k++) {
                if (value_of(cl[k]) != 0) {
                    cl[1] = cl[k];
                    cl[k] = fl;
                    vpush(watches[cl[1] ^ 1], ci);
                    moved = 1;
                    break;
                }
            }
            if (moved) continue;
            ws->d[j++] = ci;
            if (value_of(first) == 0) {
                while (i < n) ws->d[j++] = ws->d[i++];
                ws->n = j;
                return ci;
            }
            enqueue(first, ci);
        }
        ws->n = j;
    }
    return -1;
}

static void bump(int v) {
    act_v.d[v] += vinc;
    if (act_v.d[v] > 1e100) {
        for (int u = 0; u < act_v.n; u++) act_v.d[u] *= 1e-100;
        vinc *= 1e-100;
    }
    HeapItem it = {-act_v.d[v], v};
    heap_push(it);
}

static VEC(int) learnt_v;
static uint8_t *seen_buf;
static int seen_cap;

static int analyze(int ci, int *bt_out) {
    learnt_v.n = 0;
    vpush(learnt_v, 0);
    if (assign_v.n > seen_cap) {
        seen_buf = realloc(seen_buf, (size_t)assign_v.n);
        seen_cap = assign_v.n;
    }
    memset(seen_buf, 0, (size_t)assign_v.n);
    int counter = 0;
    int p = -1;
    int idx = trail_v.n;
    int cur = lim_v.n;
    for (;;) {
        int *cl = clauses.d[ci];
        int len = clause_len.d[ci];
        for (int qi = 0; qi < len; qi++) {
            int q = cl[qi];
            if (q == p) continue;
            int v = q >> 1;
            if (!seen_buf[v] && level_v.d[v] > 0) {
                seen_buf[v] = 1;
                bump(v);
                if (level_v.d[v] >= cur) counter++;
                else vpush(learnt_v, q);
            }
        }
        for (;;) {
            idx--;
            p = trail_v.d[idx];
            if (seen_buf[p >> 1]) break;
        }
        counter--;
        if (counter == 0) break;
        ci = reason_v.d[p >> 1];
    }
    learnt_v.d[0] = p ^ 1;
    if (learnt_v.n == 1) { *bt_out = 0; return 1; }
    int mi = 1;
    for (int i = 2; i < learnt_v.n; i++)
        if (level_v.d[learnt_v.d[i] >> 1] > level_v.d[learnt_v.d[mi] >> 1])
            mi = i;
    int tmp = learnt_v.d[1];
    learnt_v.d[1] = learnt_v.d[mi];
    learnt_v.d[mi] = tmp;
    *bt_out = level_v.d[learnt_v.d[1] >> 1];
    return learnt_v.n;
}

static void backtrack(int lvl) {
    if (lim_v.n <= lvl) return;
    int mark = lim_v.d[lvl];
    for (int i = mark; i < trail_v.n; i++) {
        int v = trail_v.d[i] >> 1;
        phase_v.d[v] = assign_v.d[v];
        assign_v.d[v] = -1;
        reason_v.d[v] = -1;
        HeapItem it = {-act_v.d[v], v};
        heap_push(it);
    }
    trail_v.n = mark;
    lim_v.n = lvl;
    qhead = trail_v.n;
}

static int decide(void) {
    while (heap_v.n) {
        HeapItem it = heap_pop();
        if (assign_v.d[it.var] == -1 && -it.negact == act_v.d[it.var]) {
            vpush(lim_v, trail_v.n);
            enqueue(2 * it.var + (phase_v.d[it.var] ^ 1), -1);
            return 1;
        }
    }
    for (int v = 0; v < assign_v.n; v++)
        if (assign_v.d[v] == -1) {
            vpush(lim_v, trail_v.n);
            enqueue(2 * v + (phase_v.d[v] ^ 1), -1);
            return 1;
        }
    return 0;
}

static int8_t *model_buf;

static int solve(int *assumptions, int nasm, long long budget) {
    if (!solver_ok) return ST_UNSAT;
    backtrack(0);
    long long base = conflicts;
    long long restart_at = 512, step = 512;
    for (;;) {
        int ci = propagate();
        if (ci != -1) {
            conflicts++;
            if (conflicts - base > budget) { backtrack(0); return ST_UNKNOWN; }
            if (lim_v.n <= nasm) { backtrack(0); return ST_UNSAT; }
            int bt;
            int ln = analyze(ci, &bt);
            backtrack(bt > nasm ? bt : nasm);
            if (ln >= 2) {
                int *cl = malloc(sizeof(int) * (size_t)ln);
                memcpy(cl, learnt_v.d, sizeof(int) * (size_t)ln);
                int nci = clauses.n;
                vpush(clauses, cl);
                vpush(clause_len, ln);
                vpush(watches[cl[0] ^ 1], nci);
                vpush(watches[cl[1] ^ 1], nci);
                enqueue(cl[0], nci);
            } else {
                enqueue(learnt_v.d[0], -1);
            }
            vinc /= 0.95;
            if (conflicts - base > restart_at) {
                step = step * 2 < 16384 ? step * 2 : 16384;
                restart_at = conflicts - base + step;
                backtrack(nasm);
            }
        } else {
            if (lim_v.n < nasm) {
                int a = assumptions[lim_v.n];
                if (value_of(a) == 0) { backtrack(0); return ST_UNSAT; }
                vpush(lim_v, trail_v.n);
                enqueue(a, -1);
                continue;
            }
            if (!decide()) {
                if (!model_buf) model_buf = malloc((size_t)assign_v.n);
                else model_buf = realloc(model_buf, (size_t)assign_v.n);
                memcpy(model_buf, assign_v.d, (size_t)assign_v.n);
                backtrack(0);
                return ST_SAT;
            }
        }
    }
}

/* ---------------- Tseitin (mirrors CNF) ---------------- */
static int *varof;                 /* AIG node -> CNF var + 1 (0 = none) */
static int varof_cap;
static VEC(int) tstack;

static void varof_ensure(int n) {
    if (n < varof_cap) return;
    int nc = varof_cap ? varof_cap * 2 : 1024;
    while (nc <= n) nc *= 2;
    varof = realloc(varof, sizeof(int) * (size_t)nc);
    memset(varof + varof_cap, 0, sizeof(int) * (size_t)(nc - varof_cap));
    varof_cap = nc;
}

static int enc(uint32_t aig_lit) {
    return 2 * (varof[aig_lit >> 1] - 1) | (int)(aig_lit & 1);
}

static int cnf_lit(uint32_t aig_lit) {
    if (aig_lit < 2) die("constant literal reached the CNF");
    tstack.n = 0;
    vpush(tstack, (int)(aig_lit >> 1));
    while (tstack.n) {
        int n = tstack.d[tstack.n - 1];
        varof_ensure(n);
        if (varof[n]) { tstack.n--; continue; }
        Gate g = gnodes.d[n];
        if (g.a == 0xffffffffu) {          /* leaf var */
            varof[n] = new_var() + 1;
            tstack.n--;
            continue;
        }
        int need = 0;
        uint32_t ab[2] = {g.a, g.b};
        for (int i = 0; i < 2; i++) {
            if (ab[i] > 1) {
                varof_ensure((int)(ab[i] >> 1));
                if (!varof[ab[i] >> 1]) {
                    vpush(tstack, (int)(ab[i] >> 1));
                    need = 1;
                }
            }
        }
        if (need) continue;
        tstack.n--;
        int x = new_var();
        varof[n] = x + 1;
        int la = enc(g.a);
        int lb = enc(g.b);
        int c1[2] = {2 * x + 1, la};
        int c2[2] = {2 * x + 1, lb};
        int c3[3] = {2 * x, la ^ 1, lb ^ 1};
        add_clause(c1, 2);
        add_clause(c2, 2);
        add_clause(c3, 3);
    }
    return enc(aig_lit);
}

static long long model_bits_of(Word *w) {
    long long v = 0;
    for (int i = 0; i < w->w; i++) {
        uint32_t lit = w->lit[i];
        if (lit == 1) v |= 1LL << i;
        else if (lit > 1) {
            int n = (int)(lit >> 1);
            if (n < varof_cap && varof[n]) {
                int var = varof[n] - 1;
                if (model_buf[var] == (int8_t)((lit & 1) ^ 1))
                    v |= 1LL << i;
            }
        }
    }
    return v;
}

/* wide extraction for >63-bit inputs: value as bit array */
static void model_bits_wide(Word *w, uint8_t *out) {
    for (int i = 0; i < w->w; i++) {
        uint32_t lit = w->lit[i];
        out[i] = 0;
        if (lit == 1) out[i] = 1;
        else if (lit > 1) {
            int n = (int)(lit >> 1);
            if (n < varof_cap && varof[n]) {
                int var = varof[n] - 1;
                if (model_buf[var] == (int8_t)((lit & 1) ^ 1)) out[i] = 1;
            }
        }
    }
}

/* ---------------- free_at, self-check, JSON ---------------- */
static int cmp_intp(const void *a, const void *b) {
    return *(const int *)a - *(const int *)b;
}

static int free_at(int t, int *out) {
    int n = 0;
    for (int i = 0; i < inputs_v.n; i++) out[n++] = inputs_v.d[i];
    for (int i = 0; i < states_v.n; i++) {
        int sid = states_v.d[i];
        if ((t == 0 && !has_init[sid]) || (t > 0 && !has_next[sid]))
            out[n++] = sid;
    }
    qsort(out, (size_t)n, sizeof(int), cmp_intp);
    return n;
}

/* AIG evaluation under the extracted model (for the self-check).
 * lov, when non-NULL, overrides leaf values: the array replay pins
 * base-select and array-equality leaves to their interpreter values. */
static uint8_t *aigval;
static int8_t *lov;

static void eval_aig(void) {
    aigval = realloc(aigval, (size_t)gnodes.n);
    aigval[0] = 0;
    for (int n = 1; n < gnodes.n; n++) {
        Gate g = gnodes.d[n];
        if (g.a == 0xffffffffu) {
            uint8_t v = 0;
            if (lov && lov[n] >= 0) v = (uint8_t)lov[n];
            else if (n < varof_cap && varof[n]) {
                int var = varof[n] - 1;
                if (model_buf[var] == 1) v = 1;
            }
            aigval[n] = v;
        } else {
            uint8_t va = aigval[g.a >> 1] ^ (uint8_t)(g.a & 1);
            uint8_t vb = aigval[g.b >> 1] ^ (uint8_t)(g.b & 1);
            aigval[n] = va & vb;
        }
    }
}

static uint8_t litval(uint32_t lit) {
    return aigval[lit >> 1] ^ (uint8_t)(lit & 1);
}

/* ---- concrete canonical arrays (mirrors acanon/aget for the replay) */
typedef struct { uint8_t *k, *v; } CEnt;
typedef struct { uint8_t *def; CEnt *e; int n, cap; int iw, ew; } CArr;

static void carr_reset(CArr *c) {
    for (int i = 0; i < c->n; i++) { free(c->e[i].k); free(c->e[i].v); }
    free(c->e);
    free(c->def);
    memset(c, 0, sizeof *c);
}

static void carr_push(CArr *c, const uint8_t *k, const uint8_t *v) {
    if (c->n == c->cap) {
        c->cap = c->cap ? c->cap * 2 : 8;
        c->e = realloc(c->e, sizeof(CEnt) * (size_t)c->cap);
    }
    c->e[c->n].k = malloc((size_t)(c->iw ? c->iw : 1));
    memcpy(c->e[c->n].k, k, (size_t)c->iw);
    c->e[c->n].v = malloc((size_t)(c->ew ? c->ew : 1));
    memcpy(c->e[c->n].v, v, (size_t)c->ew);
    c->n++;
}

static const uint8_t *carr_get(const CArr *c, const uint8_t *k) {
    for (int i = 0; i < c->n; i++)
        if (!memcmp(c->e[i].k, k, (size_t)c->iw)) return c->e[i].v;
    return c->def;
}

static int bits_cmp(const uint8_t *a, const uint8_t *b, int w) {
    for (int i = w - 1; i >= 0; i--) {          /* MSB first: int order */
        if (a[i] < b[i]) return -1;
        if (a[i] > b[i]) return 1;
    }
    return 0;
}

static int carr_cmp_iw;
static int carr_entcmp(const void *a, const void *b) {
    return bits_cmp(((const CEnt *)a)->k, ((const CEnt *)b)->k,
                    carr_cmp_iw);
}

static void carr_canon(CArr *c) {
    /* drop default-valued entries */
    int m = 0;
    for (int i = 0; i < c->n; i++) {
        if (!memcmp(c->e[i].v, c->def, (size_t)c->ew)) {
            free(c->e[i].k); free(c->e[i].v);
        } else c->e[m++] = c->e[i];
    }
    c->n = m;
    /* the default is the value covering the largest domain share,
     * ties to the least value; switching needs the map over half the
     * domain, so the complement enumeration stays linear */
    if (c->iw <= 62) {
        uint64_t dom = 1ull << c->iw;
        uint64_t best = dom - (uint64_t)c->n;
        const uint8_t *nd = c->def;
        for (int i = 0; i < c->n; i++) {
            uint64_t cnt = 0;
            for (int j = 0; j < c->n; j++)
                if (!memcmp(c->e[j].v, c->e[i].v, (size_t)c->ew)) cnt++;
            if (cnt > best
                || (cnt == best && bits_cmp(c->e[i].v, nd, c->ew) < 0)) {
                best = cnt;
                nd = c->e[i].v;
            }
        }
        if (nd != c->def && memcmp(nd, c->def, (size_t)c->ew)) {
            uint8_t *ndc = malloc((size_t)(c->ew ? c->ew : 1));
            memcpy(ndc, nd, (size_t)c->ew);
            CArr r;
            memset(&r, 0, sizeof r);
            r.iw = c->iw;
            r.ew = c->ew;
            r.def = ndc;
            uint8_t *kb = malloc((size_t)(c->iw ? c->iw : 1));
            for (uint64_t i = 0; i < dom; i++) {
                for (int b = 0; b < c->iw; b++)
                    kb[b] = (uint8_t)((i >> b) & 1);
                const uint8_t *v = carr_get(c, kb);
                if (memcmp(v, ndc, (size_t)c->ew)) carr_push(&r, kb, v);
            }
            free(kb);
            for (int i = 0; i < c->n; i++) { free(c->e[i].k); free(c->e[i].v); }
            free(c->e);
            free(c->def);
            *c = r;
        }
    }
    carr_cmp_iw = c->iw;
    qsort(c->e, (size_t)c->n, sizeof(CEnt), carr_entcmp);
}

static int carr_equal(const CArr *a, const CArr *b) {
    if (a->n != b->n || memcmp(a->def, b->def, (size_t)a->ew)) return 0;
    for (int i = 0; i < a->n; i++)
        if (memcmp(a->e[i].k, b->e[i].k, (size_t)a->iw)
            || memcmp(a->e[i].v, b->e[i].v, (size_t)a->ew)) return 0;
    return 1;
}

static void carr_copy(CArr *dst, const CArr *src) {
    memset(dst, 0, sizeof *dst);
    dst->iw = src->iw;
    dst->ew = src->ew;
    dst->def = malloc((size_t)(src->ew ? src->ew : 1));
    memcpy(dst->def, src->def, (size_t)src->ew);
    for (int i = 0; i < src->n; i++) carr_push(dst, src->e[i].k, src->e[i].v);
}

static void litval_bits(const uint32_t *lits, int n, uint8_t *out) {
    for (int i = 0; i < n; i++) out[i] = litval(lits[i]);
}

/* The interpreter-faithful replay: pin base-select leaves to reads of
 * the concrete canonical arrays (built from the extracted stimulus,
 * model side) and array-equality leaves to canonical equality, then
 * re-evaluate the circuit; iterate to fixpoint over the DAG. */
static void replay_arrays(void) {
    lov = malloc((size_t)gnodes.n);
    memset(lov, 0xff, (size_t)gnodes.n);
    CArr *conc = calloc((size_t)(aterms.n ? aterms.n : 1), sizeof(CArr));
    for (int pass = 0; pass < 200; pass++) {
        eval_aig();
        for (int aid = 1; aid < aterms.n; aid++) {
            carr_reset(&conc[aid]);
            const AT *a = &aterms.d[aid];
            CArr *c = &conc[aid];
            if (a->kind == AT_BASE) {
                c->iw = a->iw;
                c->ew = a->ew;
                c->def = calloc((size_t)(a->ew ? a->ew : 1), 1);
                uint8_t *ib = malloc((size_t)(a->iw ? a->iw : 1));
                uint8_t *vb = malloc((size_t)(a->ew ? a->ew : 1));
                for (int s = 0; s < base_sels[aid].n; s++) {
                    Sel *sl = &base_sels[aid].d[s];
                    Word wi = {sl->idx, a->iw}, wv = {sl->w, a->ew};
                    model_bits_wide(&wi, ib);
                    model_bits_wide(&wv, vb);
                    int dup = 0;
                    for (int u = 0; u < c->n; u++)
                        if (!memcmp(c->e[u].k, ib, (size_t)a->iw)) {
                            dup = 1;
                            break;
                        }
                    if (!dup) carr_push(c, ib, vb);
                }
                free(ib);
                free(vb);
                carr_canon(c);
            } else if (a->kind == AT_CONST) {
                c->iw = a->iw;
                c->ew = a->ew;
                c->def = malloc((size_t)(a->ew ? a->ew : 1));
                litval_bits(a->cw, a->ew, c->def);
            } else if (a->kind == AT_WRITE) {
                carr_copy(c, &conc[a->sub]);
                uint8_t *ib = malloc((size_t)(a->iw ? a->iw : 1));
                uint8_t *vb = malloc((size_t)(a->ew ? a->ew : 1));
                litval_bits(a->idx, a->iw, ib);
                litval_bits(a->val, a->ew, vb);
                int hit = 0;
                for (int u = 0; u < c->n; u++)
                    if (!memcmp(c->e[u].k, ib, (size_t)a->iw)) {
                        memcpy(c->e[u].v, vb, (size_t)a->ew);
                        hit = 1;
                        break;
                    }
                if (!hit) carr_push(c, ib, vb);
                free(ib);
                free(vb);
                carr_canon(c);
            } else {
                carr_copy(c, litval(a->cond) ? &conc[a->sub]
                                             : &conc[a->sub2]);
            }
        }
        int changed = 0;
        for (int aid = 1; aid < aterms.n; aid++) {
            if (aterms.d[aid].kind != AT_BASE) continue;
            const AT *a = &aterms.d[aid];
            uint8_t *ib = malloc((size_t)(a->iw ? a->iw : 1));
            for (int s = 0; s < base_sels[aid].n; s++) {
                Sel *sl = &base_sels[aid].d[s];
                litval_bits(sl->idx, a->iw, ib);
                const uint8_t *vb = carr_get(&conc[aid], ib);
                for (int b = 0; b < a->ew; b++) {
                    int n = (int)(sl->w[b] >> 1);
                    if (lov[n] != (int8_t)vb[b]) {
                        lov[n] = (int8_t)vb[b];
                        changed = 1;
                    }
                }
            }
            free(ib);
        }
        if (eqh.e)
            for (uint32_t i = 0; i <= eqh.mask; i++) {
                if (!eqh.e[i].used) continue;
                int8_t verdict = (int8_t)carr_equal(&conc[eqh.e[i].aA],
                                                    &conc[eqh.e[i].aB]);
                int n = (int)(eqh.e[i].e >> 1);
                if (lov[n] != verdict) {
                    lov[n] = verdict;
                    changed = 1;
                }
            }
        if (!changed) break;
    }
    eval_aig();
    for (int aid = 1; aid < aterms.n; aid++) carr_reset(&conc[aid]);
    free(conc);
}

/* JSON: emit one frame dict with sorted string keys                 */
typedef struct { char *k; uint8_t *vb; int vw; } AEnt;
typedef struct { char key[16]; uint8_t *bits; int w;
                 int is_arr; AEnt *ae; int nae; } Ent;

static int cmp_aent(const void *a, const void *b) {
    return strcmp(((const AEnt *)a)->k, ((const AEnt *)b)->k);
}

static char *bits_to_dec(const uint8_t *bits, int w) {
    char *dec = calloc((size_t)w / 3 + 4, 1);
    int dn = 1;
    for (int i = w - 1; i >= 0; i--) {
        int carry = bits[i];
        for (int j = 0; j < dn; j++) {
            int cur = dec[j] * 2 + carry;
            dec[j] = (char)(cur % 10);
            carry = cur / 10;
        }
        while (carry) { dec[dn++] = (char)(carry % 10); carry /= 10; }
    }
    char *s = malloc((size_t)dn + 1);
    for (int j = 0; j < dn; j++) s[j] = (char)('0' + dec[dn - 1 - j]);
    s[dn] = 0;
    free(dec);
    return s;
}

static int cmp_ent(const void *a, const void *b) {
    return strcmp(((const Ent *)a)->key, ((const Ent *)b)->key);
}

static void print_bits_decimal(uint8_t *bits, int w) {
    /* binary -> decimal string, arbitrary width */
    char *dec = calloc((size_t)w / 3 + 4, 1);
    int dn = 1;
    dec[0] = 0;
    for (int i = w - 1; i >= 0; i--) {
        int carry = bits[i];
        for (int j = 0; j < dn; j++) {
            int cur = dec[j] * 2 + carry;
            dec[j] = (char)(cur % 10);
            carry = cur / 10;
        }
        while (carry) { dec[dn++] = (char)(carry % 10); carry /= 10; }
    }
    for (int j = dn - 1; j >= 0; j--) putchar('0' + dec[j]);
    free(dec);
}

/* ---------------- the BMC loop (mirrors bmc()) ---------------- */
static const char *NOTE = NULL;
static int witness_depth = -1;
static VEC(Ent) *wit_frames;

int main(int argc, char **argv) {
    if (argc < 6) die("usage: solve_fast <prog> <mode> <obs> <bound> <wall>");
    const char *observable = argv[3];
    if (strcmp(observable, "bad")) {
        printf("{\"kind\": \"partial\", \"progress\": {\"note\": "
               "\"btor2-bmcf only decides 'bad'\"}}\n");
        return 0;
    }
    parse_file(argv[1]);
    int bound_inf = !strcmp(argv[4], "inf");
    long long bound = bound_inf ? 0 : atoll(argv[4]);
    double wall_s = atof(argv[5]);
    long long budget = (long long)(400.0 * wall_s);
    if (budget < 2000) budget = 2000;
    long long clause_cap = (long long)(30000.0 * wall_s);
    if (clause_cap > 18000000) clause_cap = 18000000;
    if (clause_cap < 20000) clause_cap = 20000;
    long long node_cap = (long long)(20000.0 * wall_s);
    if (node_cap > 12000000) node_cap = 12000000;
    if (node_cap < 4000000) node_cap = 4000000;
    long long inf_cap = 300;

    aig_init();
    ensure_frame(0);

    long long proven = -1;
    long long k = 0;
    long long vacuous_from = -1;
    int result = -1;               /* 0 all, 1 witness, 2 partial */
    long long all_bound = 0;
    int all_is_inf = 0;

    VEC(int) asm_v = {0};
    while (bound_inf || k <= bound) {
        if (bound_inf && k > inf_cap) { NOTE = "inf depth cap"; result = 2; break; }
        if (vacuous_from >= 0) { result = 0; all_is_inf = 1; break; }
        if (gnodes.n > node_cap) { NOTE = "AIG node cap"; result = 2; break; }
        if (clauses.n > clause_cap) { NOTE = "CNF size cap"; result = 2; break; }
        asm_v.n = 0;
        int dead = 0;
        for (long long t = 0; t <= k; t++) {
            uint32_t c = constraint_at((int)t);
            if (c == 0) { vacuous_from = t; dead = 1; break; }
            if (c != 1) vpush(asm_v, cnf_lit(c));
        }
        if (!dead) {
            uint32_t b = bad_at((int)k);
            if (b == 0) { proven = k; k++; continue; }
            for (int ai = 0; ai < axioms_v.n; ai++) {
                uint32_t ax = axioms_v.d[ai];
                if (ax == 0)
                    partial_exit("internal: contradictory array axiom");
                if (ax != 1) vpush(asm_v, cnf_lit(ax));
            }
            if (b != 1) vpush(asm_v, cnf_lit(b));
            int status = solve(asm_v.d, asm_v.n, budget - conflicts);
            if (status == ST_UNKNOWN) { NOTE = "conflict budget spent"; result = 2; break; }
            if (status == ST_SAT) {
                /* extract witness frames */
                wit_frames = calloc((size_t)k + 1, sizeof(*wit_frames));
                int *fr = malloc(sizeof(int) * (size_t)(inputs_v.n + states_v.n + 1));
                for (long long t = 0; t <= k; t++) {
                    int n = free_at((int)t, fr);
                    for (int i = 0; i < n; i++) {
                        if (nodes[fr[i]].is_arr) {
                            /* mirrors: aval = bl.words.get((nid, t));
                             * entries.setdefault(model idx, model val) */
                            if (!havew[t][fr[i]]) continue;
                            int aid = -frames[t][fr[i]].w;
                            int iw = aterms.d[aid].iw;
                            int ew = aterms.d[aid].ew;
                            AEnt *ae = NULL;
                            int nae = 0, cap = 0;
                            for (int s = 0; s < base_sels[aid].n; s++) {
                                Sel *sl = &base_sels[aid].d[s];
                                Word wi = {sl->idx, iw}, wv = {sl->w, ew};
                                uint8_t *ib = malloc((size_t)(iw ? iw : 1));
                                uint8_t *vb = malloc((size_t)(ew ? ew : 1));
                                model_bits_wide(&wi, ib);
                                model_bits_wide(&wv, vb);
                                char *ks = bits_to_dec(ib, iw);
                                free(ib);
                                int dup = 0;
                                for (int u = 0; u < nae; u++)
                                    if (!strcmp(ae[u].k, ks)) { dup = 1; break; }
                                if (dup) { free(ks); free(vb); continue; }
                                if (nae == cap) {
                                    cap = cap ? cap * 2 : 8;
                                    ae = realloc(ae, sizeof(AEnt) * (size_t)cap);
                                }
                                ae[nae].k = ks;
                                ae[nae].vb = vb;
                                ae[nae].vw = ew;
                                nae++;
                            }
                            if (nae) {
                                Ent e;
                                memset(&e, 0, sizeof e);
                                snprintf(e.key, sizeof e.key, "%d", fr[i]);
                                e.is_arr = 1;
                                e.ae = ae;
                                e.nae = nae;
                                vpush(wit_frames[t], e);
                            } else free(ae);
                            continue;
                        }
                        Word *w = word_of(fr[i], (int)t);
                        uint8_t *bits = malloc((size_t)(w->w ? w->w : 1));
                        model_bits_wide(w, bits);
                        int nz = 0;
                        for (int bb = 0; bb < w->w; bb++) nz |= bits[bb];
                        if (nz) {
                            Ent e;
                            memset(&e, 0, sizeof e);
                            snprintf(e.key, sizeof e.key, "%d", fr[i]);
                            e.bits = bits;
                            e.w = w->w;
                            vpush(wit_frames[t], e);
                        } else free(bits);
                    }
                }
                free(fr);
                /* self-check: circuit replay for pure bitvec; the
                 * interpreter-faithful override replay for arrays */
                if (!have_arrays) eval_aig();
                else replay_arrays();
                int fired = -1;
                int constrained = 1;
                for (long long t = 0; t <= k && fired < 0; t++) {
                    if (constrained) {
                        uint32_t c = constraint_at((int)t);
                        if (c != 1 && (c == 0 || !litval(c)))
                            constrained = 0;
                    }
                    if (constrained) {
                        uint32_t b2 = bad_at((int)t);
                        if (b2 == 1 || (b2 > 1 && litval(b2)))
                            fired = (int)t;
                    }
                }
                if (fired != (int)k) {
                    static char nbuf[80];
                    snprintf(nbuf, sizeof nbuf,
                             "internal: model did not replay at depth %lld", k);
                    NOTE = nbuf;
                    result = 2;
                    break;
                }
                witness_depth = (int)k;
                result = 1;
                break;
            }
            proven = k;
            if (conflicts >= budget) { NOTE = "conflict budget spent"; result = 2; break; }
        } else {
            if (proven >= vacuous_from - 1) { result = 0; all_is_inf = 1; break; }
            NOTE = "constraints impossible yet unproven";
            result = 2;
            break;
        }
        k++;
    }
    if (result == -1) { result = 0; all_bound = bound; }

    if (result == 1) {
        printf("{\"depth\": %d, \"kind\": \"witness\", \"payload\": "
               "{\"steps\": [", witness_depth);
        for (int t = 0; t <= witness_depth; t++) {
            if (t) printf(", ");
            qsort(wit_frames[t].d, (size_t)wit_frames[t].n, sizeof(Ent),
                  cmp_ent);
            putchar('{');
            for (int i = 0; i < wit_frames[t].n; i++) {
                if (i) printf(", ");
                printf("\"%s\": ", wit_frames[t].d[i].key);
                if (wit_frames[t].d[i].is_arr) {
                    Ent *e = &wit_frames[t].d[i];
                    qsort(e->ae, (size_t)e->nae, sizeof(AEnt), cmp_aent);
                    printf("{\"default\": 0, \"set\": {");
                    for (int u = 0; u < e->nae; u++) {
                        if (u) printf(", ");
                        printf("\"%s\": ", e->ae[u].k);
                        print_bits_decimal(e->ae[u].vb, e->ae[u].vw);
                    }
                    printf("}}");
                } else {
                    print_bits_decimal(wit_frames[t].d[i].bits,
                                       wit_frames[t].d[i].w);
                }
            }
            putchar('}');
        }
        printf("]}}\n");
    } else if (result == 0) {
        if (all_is_inf) printf("{\"bound\": \"inf\", \"kind\": \"all\"}\n");
        else printf("{\"bound\": %lld, \"kind\": \"all\"}\n", all_bound);
    } else {
        if (proven >= 0)
            printf("{\"bound\": %lld, \"kind\": \"all\"}\n", proven);
        else
            printf("{\"kind\": \"partial\", \"progress\": {\"note\": "
                   "\"%s\"}}\n", NOTE);
    }
    return 0;
}
