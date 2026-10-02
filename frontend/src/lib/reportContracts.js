const DEFAULT_CONTRACT = {
  dataSource: 'PMS işlem kayıtları',
  dateScope: 'Ekranda seçilen rapor dönemi',
  financialScope: 'Rapor türüne göre tahakkuk, folyo hareketi veya tahsilat',
  currencyRule: 'Farklı para birimleri dönüştürülmeden toplanmaz; ayrı gösterilir.',
};

const FINANCIAL_CONTRACT = {
  ...DEFAULT_CONTRACT,
  dataSource: 'Onaylı folyo hareketleri, rezervasyon gece kayıtları ve ödeme kayıtları',
  financialScope: 'Tahsilat, oda geliri ve fiyat düzeltmesi ayrı kalemlerdir.',
};

export const REPORT_CONTRACTS = {
  overview: { ...FINANCIAL_CONTRACT, dateScope: 'Seçilen gün veya son 30 gün' },
  revenue: { ...FINANCIAL_CONTRACT, financialScope: 'Gelir; tahsilat yerine geçmez. İptal ve fiyat düzeltmeleri ayrı gösterilir.' },
  adr_revpar: {
    ...FINANCIAL_CONTRACT,
    financialScope: 'ADR = oda geliri / satılan oda-gecesi. RevPAR = oda geliri / satılabilir oda-gecesi.',
  },
  occupancy: { ...DEFAULT_CONTRACT, dataSource: 'Satılabilir oda envanteri ve konaklama gece kayıtları', financialScope: 'Finansal tutar içermez.' },
  payments: { ...FINANCIAL_CONTRACT, dateScope: 'Seçili iş günü', financialScope: 'Yalnızca geçerli tahsilat ve iade hareketleri; fiyat düzeltmeleri hariçtir.' },
  front_cashier: { ...FINANCIAL_CONTRACT, dateScope: 'Seçili iş günü', financialScope: 'Folyo hareketleri ve geçerli tahsilatlar ayrı hesaplanır.' },
  cash_movements: { ...FINANCIAL_CONTRACT, dateScope: 'Seçili iş günü', financialScope: 'Yalnızca geçerli tahsilat ve iade hareketleri.' },
  rate_control: { ...DEFAULT_CONTRACT, dataSource: 'Rezervasyon gece fiyatları ve folyo oda tahakkukları', financialScope: 'Fiyat farkı tahsilat değildir; yalnızca mutabakat farkı olarak gösterilir.' },
  trial_balance: { ...FINANCIAL_CONTRACT, dataSource: 'Operasyon, folyo ve ödeme mutabakat kayıtları' },
  gl_trial_balance: { ...DEFAULT_CONTRACT, dataSource: 'Onaylanmış genel muhasebe fişleri', financialScope: 'Muhasebeleşmiş borç ve alacak bakiyeleri.' },
  income_statement: { ...DEFAULT_CONTRACT, dataSource: 'Onaylanmış genel muhasebe fişleri', financialScope: 'Muhasebeleşmiş gelir, gider ve dönem sonucu.' },
  balance_sheet: { ...DEFAULT_CONTRACT, dataSource: 'Onaylanmış genel muhasebe fişleri', financialScope: 'Rapor tarihi itibarıyla varlık, yükümlülük ve özkaynak.' },
  journal: { ...DEFAULT_CONTRACT, dataSource: 'Onaylanmış genel muhasebe fişleri', financialScope: 'Yevmiye hareketleri; taslak fişler hariçtir.' },
  official: { ...DEFAULT_CONTRACT, dataSource: 'Seçili tarihteki misafir ve konaklama kayıtları', financialScope: 'Resmî liste; finansal toplamlar yalnızca bilgi amaçlıdır.' },
  police: { ...DEFAULT_CONTRACT, dataSource: 'Seçili tarihte fiilen konaklayan misafir kayıtları', financialScope: 'Finansal tutar içermez.' },
};

export function getReportContract(section) {
  return REPORT_CONTRACTS[section] || DEFAULT_CONTRACT;
}
