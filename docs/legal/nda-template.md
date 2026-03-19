# 秘密保持契約書 / Non-Disclosure Agreement

> **注意**: 本書はドラフトです。正式な法的効力を持たせるには、有資格の法律専門家による審査が必要です。
>
> **NOTICE**: This document is a draft. It must be reviewed by qualified legal counsel before use as a binding agreement.

---

## 秘密保持契約書

本秘密保持契約書（以下「本契約」という）は、以下の当事者間において締結される。

**開示者（Disclosing Party）:**
前田雄太郎（以下「開示者」という）

**受領者（Receiving Party）:**
名称: _______________________________________________
担当者: _______________________________________________
役職: _______________________________________________
住所: _______________________________________________

開示者および受領者を総称して「両当事者」という。

---

## 第1条　秘密情報の定義（Definition of Confidential Information）

1.1 本契約において「秘密情報」とは、開示者が受領者に対して開示する以下の情報をいう（開示の形式が書面、口頭、電子媒体その他を問わない）。

   (a) FaultRayソフトウェア（ソースコード、バイナリ、モジュール、ライブラリ、コンパイル済みコードを含む）

   (b) インフラシミュレーションエンジンおよびカオスエンジニアリングアルゴリズム（設計思想、数学的モデル、実装方法を含む）

   (c) 特許出願前の技術情報（発明の詳細、技術的手法、プロセス、革新的要素を含む）

   (d) 製品ロードマップ、事業計画、価格戦略、顧客情報

   (e) APIドキュメント、技術仕様書、設計書、アーキテクチャ図

   (f) βテスト環境へのアクセス資格情報（IDおよびパスワード）

   (g) DORA（Digital Operational Resilience Act）対応機能の詳細実装

   (h) 前各号に関連するすべての派生的情報、分析結果、評価結果

1.2 秘密情報であることの表示が省略された場合であっても、開示の状況から秘密情報であることが合理的に認識できる情報は、本契約の秘密情報に含まれる。

---

*English Reference — Article 1: "Confidential Information" means all information disclosed by the Disclosing Party to the Receiving Party in any form (written, oral, electronic, or otherwise), including but not limited to: FaultRay software (source code, binaries, modules, libraries); simulation and chaos engineering algorithms; pre-patent-filing technical information; product roadmaps; business plans; API documentation; beta access credentials; DORA compliance implementation details; and any derivative information thereof.*

---

## 第2条　秘密保持義務（Obligations of Confidentiality）

2.1 受領者は、秘密情報を厳格に秘密として保持し、以下の義務を負う。

   (a) 開示者の事前の書面による承諾なく、秘密情報を第三者に開示、公開、提供、または漏洩しないこと

   (b) 秘密情報へのアクセスを、本βテスト評価の目的を達成するために知る必要がある自社の役員および従業員（以下「知る必要のある者」という）に限定すること

   (c) 秘密情報を開示する知る必要のある者に対して、本契約と同等以上の秘密保持義務を課すこと

   (d) 秘密情報の保護のために、自社の同等の秘密情報の保護に用いるものと同等以上の注意を払うこと（ただし、いかなる場合においても合理的な注意を下回らないこと）

   (e) 本βテスト評価期間終了後または開示者の書面による要求があった場合、受領者の管理下にあるすべての秘密情報（コピーおよび複製物を含む）を直ちに返還または破棄すること

2.2 受領者は、秘密情報の不正な開示または利用が生じたことを知った場合、直ちに開示者に書面により通知するとともに、損害の拡大防止に協力するものとする。

---

*English Reference — Article 2: The Receiving Party shall hold all Confidential Information in strict confidence, shall not disclose it to any third party without prior written consent, shall restrict access only to employees who need to know it for the beta evaluation purpose, and shall apply at least the same degree of care as it uses for its own confidential information.*

---

## 第3条　除外事項（Exclusions）

3.1 以下の情報は、本契約における秘密情報から除外される。

   (a) 受領者が受領した時点において既に公知であった情報（受領者の行為によらずに公知となったものを含む）

   (b) 受領者が開示者から受領した後に、受領者の帰責事由によらず公知となった情報

   (c) 受領者が秘密情報の受領以前から適法に保有していた情報（立証書類により証明されるものに限る）

   (d) 受領者が本契約に違反することなく第三者から適法に取得した情報

   (e) 受領者が秘密情報を参照することなく独自に開発した情報（独自開発の立証は受領者が負う）

   (f) 法令、裁判所の命令、または行政機関の要請に基づき開示が義務付けられた情報（ただし受領者は開示前に開示者に書面による通知を行い、開示の範囲を最小限にとどめるよう努めるものとする）

---

*English Reference — Article 3: Exclusions apply to information that: (a) was in the public domain at the time of disclosure; (b) became public through no fault of the Receiving Party; (c) was lawfully in the Receiving Party's possession before disclosure; (d) was lawfully received from a third party; (e) was independently developed without reference to Confidential Information; or (f) must be disclosed by law or court order (with prior written notice to Disclosing Party).*

---

## 第4条　有効期間（Term）

4.1 本契約は、両当事者の署名日（以下「契約日」という）から効力を生じ、契約日から**3年間**有効とする。

4.2 前項の期間満了後も、本契約締結中に開示された秘密情報に関する秘密保持義務は、契約期間中と同一の条件で存続するものとする。

4.3 いずれの当事者も、相手方に対して30日前に書面による通知を行うことにより、本契約を解除することができる。ただし、解除前に開示された秘密情報に関する秘密保持義務は本契約満了後も存続するものとする。

---

*English Reference — Article 4: This Agreement is effective as of the date of signature and remains in force for three (3) years. Confidentiality obligations survive termination for information disclosed during the term. Either party may terminate with 30 days' written notice; obligations for previously disclosed information survive.*

---

## 第5条　βテスト評価目的の限定使用（Permitted Use — Beta Evaluation Only）

5.1 受領者は、秘密情報をFaultRayのβテスト評価（以下「評価目的」という）にのみ使用することができ、その他のいかなる目的にも使用してはならない。

5.2 受領者は、以下の行為を明示的に禁止される。

   (a) 秘密情報の商業的利用（評価目的以外での内部業務利用を含む）

   (b) 秘密情報を基にした類似製品、競合製品、または代替製品の開発

   (c) 秘密情報のリバースエンジニアリング、逆コンパイル、または逆アセンブル

   (d) FaultRayのアルゴリズムまたは技術的手法を模倣した製品の開発

   (e) 秘密情報の第三者へのサブライセンスまたは転送

---

*English Reference — Article 5: Confidential Information may be used solely for the purpose of beta testing and evaluating FaultRay. Commercial use, development of competing products, reverse engineering, decompilation, disassembly, or sublicensing of Confidential Information is expressly prohibited.*

---

## 第6条　知的財産権（Intellectual Property Rights）

6.1 本契約に基づく秘密情報の開示は、いかなる意味においても、開示者から受領者への知的財産権の移転、実施許諾、またはその他の権利付与を意味するものではない。

6.2 FaultRayに関連するすべての知的財産権（特許権、実用新案権、著作権、商標権、営業秘密を含むがこれらに限られない）は、開示者である前田雄太郎に帰属し、かつ帰属し続けるものとする。

6.3 受領者が評価過程において開示者の秘密情報を使用または参照して案出した改良、派生発明、または創作物（以下「派生物」という）については、受領者は開示者に対して速やかに書面により開示するものとし、当該派生物に関する権利は開示者に帰属するものとする。

6.4 受領者は、開示者の明示的な書面による事前承諾なく、秘密情報について知的財産権の登録出願を行ってはならない。

---

*English Reference — Article 6: Disclosure of Confidential Information does not transfer any intellectual property rights. All IP rights related to FaultRay—including patents, copyrights, trade secrets, and trademarks—remain exclusively with the Disclosing Party, Yutaro Maeda. Any improvements or derivatives created using Confidential Information shall be disclosed to and owned by the Disclosing Party.*

---

## 第7条　特許出願への非影響（No Impact on Patent Filing）

7.1 本契約に基づく秘密情報の開示は、開示者が将来行う特許出願において先行技術を構成しないことを確認する。両当事者は、本契約に基づく開示が秘密保持義務の下で行われるものであることを確認し、当該開示が公開にあたらないことに同意する。

7.2 受領者は、開示者が特許出願を行う権利を妨げる行為（本契約に基づく開示を公知と主張すること、または先行技術として援用することを含む）を行ってはならない。

7.3 受領者は、本契約に基づき受領した技術情報について、特許庁その他の公的機関への申告または提出を行ってはならない（開示者の書面による事前承諾がある場合を除く）。

---

*English Reference — Article 7: Disclosure of Confidential Information under this Agreement shall not constitute prior art for any patent application by the Disclosing Party. Both parties acknowledge that disclosures made under this Agreement are confidential and do not constitute public disclosure. The Receiving Party shall not take any action that could impair the Disclosing Party's patent rights.*

---

## 第8条　準拠法および管轄（Governing Law and Jurisdiction）

8.1 本契約は、日本国法に準拠し、解釈されるものとする。

8.2 本契約に関連して生じる紛争については、東京地方裁判所を第一審の専属的合意管轄裁判所とする。

8.3 本契約の解釈について日本語版と英語版の間に齟齬がある場合は、日本語版が優先するものとする。

---

*English Reference — Article 8: This Agreement is governed by the laws of Japan. Any disputes shall be subject to the exclusive jurisdiction of the Tokyo District Court as the court of first instance. In the event of any inconsistency between the Japanese and English versions, the Japanese version shall prevail.*

---

## 第9条　一般条項（General Provisions）

9.1 **完全合意**: 本契約は、本件に関する両当事者間の完全な合意を構成し、以前の交渉、覚書、口頭合意その他すべての事前の合意に優先する。

9.2 **変更**: 本契約の変更は、両当事者が署名した書面によるものでなければ効力を生じない。

9.3 **権利の不放棄**: いずれかの当事者が本契約上の権利を行使しないことは、当該権利の放棄とみなされない。

9.4 **可分性**: 本契約の一部が無効または執行不能となった場合においても、残余の条項の効力には影響しない。

9.5 **差止救済**: 受領者による本契約違反が、開示者に対して回復不能な損害を与えることを両当事者は認識し、開示者が差止命令その他の衡平法上の救済を求める権利を有することに同意する。

9.6 **通知**: 本契約に関するすべての通知は、書面により各当事者の署名時の住所宛てに行うものとする。

---

## 署名欄（Signature Block）

本契約の成立を証するため、両当事者は本書2通を作成し、各自1通を保有する。

---

### 開示者（Disclosing Party）

```
氏名（署名）:  前田雄太郎
Name:          Yutaro Maeda

肩書き:        FaultRay 代表 / Creator
Title:         Founder, FaultRay

住所:
Address:

署名:          _______________________________

日付 / Date:   ___________年___________月___________日
```

---

### 受領者（Receiving Party）

```
会社名（法人名）/ Company Name:

  _____________________________________________

担当者氏名 / Representative Name:

  _____________________________________________

肩書き / Title:

  _____________________________________________

住所 / Address:

  _____________________________________________
  _____________________________________________

署名 / Signature:

  _____________________________________________

日付 / Date:   ___________年___________月___________日
```

---

*本文書はFaultRay βテスト評価開始前に必ず締結してください。*
*This agreement must be executed prior to commencement of any FaultRay beta evaluation.*
