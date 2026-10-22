import { EXELY_DEMOGRAPHICS_WARNING, exelyDemographicsUnverified } from '@/utils/exelyDemographics';

export default function ExelyDemographicsNotice({ booking }) {
  if (!exelyDemographicsUnverified(booking)) return null;
  return <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900" data-testid="exely-demographics-warning">
    {EXELY_DEMOGRAPHICS_WARNING}
  </p>;
}
