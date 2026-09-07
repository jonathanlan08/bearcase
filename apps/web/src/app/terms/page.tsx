import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage, LegalSection } from "@/components/account/legal";

export const metadata: Metadata = { title: "Terms of use", description: "Plain-language terms for using BearCase. A template; have a lawyer review before use." };

export default function TermsPage() {
  return (
    <LegalPage title="Terms of use." lede="What you agree to when you create an account, upload a document, or buy a pilot." updated="September 2026">
      <LegalSection title="1. What BearCase is">
        <p>BearCase reads the documents you upload for a business acquisition, checks the seller&apos;s claims against the financial statements, recomputes figures with a deterministic engine, and shows you what to investigate. It is a review tool. It does not give investment, legal, tax, or accounting advice, and nothing it produces is a recommendation to buy, not buy, or pay a price.</p>
      </LegalSection>
      <LegalSection title="2. Your account">
        <p>You need an account with a working email address to keep deals. You are responsible for the password and for what happens under your account. Verify the address when asked; sharing a deal with a collaborator requires it. Demo sessions are separate temporary identities and are removed as described on the trust page.</p>
      </LegalSection>
      <LegalSection title="3. Your documents">
        <p>You keep every right to what you upload. Upload only documents you are permitted to share; a seller&apos;s confidential materials usually come with a non-disclosure agreement, and it is yours to honour. We process the documents to provide the service and for nothing else. You can delete a document or a deal at any time, and deletion does what the trust page says it does.</p>
        <p>Uploaded documents are treated as untrusted content: the software never runs instructions found in a document, and text that looks like an instruction to the assistant is flagged rather than followed.</p>
      </LegalSection>
      <LegalSection title="4. Sharing a deal">
        <p>An owner may invite a collaborator to a deal as a viewer or an editor. Members act under their own account and their actions are recorded in the audit history. The owner can remove a member at any time and a member can leave. The owner remains responsible for who was given access.</p>
      </LegalSection>
      <LegalSection title="5. What the output means">
        <p>Every statement is marked as a source fact, a calculation, an assumption, or an AI interpretation. A citation shows where a statement came from; it does not establish that the statement is true. The original AI output is never altered; reviewer decisions are recorded alongside it. You are responsible for reading the sources before you rely on anything BearCase shows you.</p>
      </LegalSection>
      <LegalSection title="6. The assistant and third-party models">
        <p>When a model provider is connected, the assistant sends claim text, evidence snippets, and a one-page deal brief to that provider, and if you switch the document reader to a model, document text as well. The provider is named in the panel and on the trust page. Their terms apply to what they receive. With no provider connected, nothing leaves the server.</p>
      </LegalSection>
      <LegalSection title="7. Limits and fair use">
        <p>The service has quotas: a number of documents per deal, a storage limit per account, a monthly number of assistant answers, and request rate limits. The app tells you when you reach one. Do not probe, overload, or attempt to access another account&apos;s deals.</p>
      </LegalSection>
      <LegalSection title="8. Paying for a pilot">
        <p>The bounded pilot described on <Link href="/pilot" className="text-fg underline underline-offset-2">the pilot page</Link> is paid in advance through Stripe. The price shown at checkout is the price. If we cannot deliver within the stated scope, we refund the fee in full; the deliverables and their limitations are those listed on that page.</p>
      </LegalSection>
      <LegalSection title="9. No warranty, limited liability">
        <p>BearCase is provided as it is. We do not warrant that it finds every inconsistency or that any figure is correct. To the extent the law allows, we are not liable for decisions made on the basis of its output, and our total liability for a paid pilot is limited to the fee paid for it.</p>
      </LegalSection>
      <LegalSection title="10. Changes and ending the service">
        <p>We may change these terms; the date above moves when we do, and material changes are announced in the app. You can stop using the service at any time and delete your documents. We may suspend an account that breaks these terms.</p>
      </LegalSection>
      <LegalSection title="11. Contact">
        <p>Questions about these terms go to the address in the footer of the pilot page{process.env.NEXT_PUBLIC_CONTACT_EMAIL ? <>: <a href={`mailto:${process.env.NEXT_PUBLIC_CONTACT_EMAIL}`} className="text-fg underline underline-offset-2">{process.env.NEXT_PUBLIC_CONTACT_EMAIL}</a></> : ""}.</p>
      </LegalSection>
    </LegalPage>
  );
}
