#
# Copyright (C) 2007-2013 by frePPLe bvba
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero
# General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import json

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connections
from django.utils.translation import ugettext_lazy as _
from django.utils.text import capfirst
from django.utils.encoding import force_text

from django.http import HttpResponseForbidden, HttpResponse, HttpResponseBadRequest
from freppledb.input.models import Item, PurchaseOrder, DistributionOrder, OperationPlan
from freppledb.output.models import Demand, DemandPegging
from freppledb.common.db import python_date
from freppledb.common.report import GridReport, GridPivot, GridFieldText, GridFieldNumber, GridFieldDateTime, GridFieldInteger


class OverviewReport(GridPivot):
  '''
  A report showing the independent demand for each item.
  '''
  template = 'output/demand.html'
  title = _('Demand report')
  basequeryset = Item.objects.all()
  model = Item
  permissions = (("view_demand_report", "Can view demand report"),)
  rows = (
    GridFieldText('item', title=_('item'), key=True, editable=False, field_name='name', formatter='detail', extra="role:'input/item'"),
    )
  crosses = (
    ('demand', {'title': _('demand')}),
    ('supply', {'title': _('supply')}),
    ('backlog', {'title': _('backlog')}),
    )

  @classmethod
  def extra_context(reportclass, request, *args, **kwargs):
    if args and args[0]:
      request.session['lasttab'] = 'plan'
      return {
        'title': capfirst(force_text(Item._meta.verbose_name) + " " + args[0]),
        'post_title': ': ' + capfirst(force_text(_('plan'))),
        }
    else:
      return {}

  @staticmethod
  def query(request, basequery, sortsql='1 asc'):
    basesql, baseparams = basequery.query.get_compiler(basequery.db).as_sql(with_col_aliases=False)
    cursor = connections[request.database].cursor()

    # Assure the item hierarchy is up to date
    Item.rebuildHierarchy(database=basequery.db)

    # Execute a query to get the backlog at the start of the horizon
    startbacklogdict = {}
    query = '''
      select items.name, sum(quantity)
      from (%s) items
      inner join item
      on item.lft between items.lft and items.rght
      inner join out_demand
      on item.name = out_demand.item
        and (plandate is null or plandate >= '%s')
        and due < '%s'
      group by items.name
      ''' % (basesql, request.report_startdate, request.report_startdate)
    cursor.execute(query, baseparams)
    for row in cursor.fetchall():
      if row[0]:
        startbacklogdict[row[0]] = float(row[1])

    # Execute the query
    query = '''
        select y.name as row1,
               y.bucket as col1, y.startdate as col2, y.enddate as col3,
               min(y.orders),
               min(y.planned)
        from (
          select x.name as name, x.lft as lft, x.rght as rght,
               x.bucket as bucket, x.startdate as startdate, x.enddate as enddate,
               coalesce(sum(demand.quantity),0) as orders,
               min(x.planned) as planned
          from (
          select items.name as name, items.lft as lft, items.rght as rght,
                 d.bucket as bucket, d.startdate as startdate, d.enddate as enddate,
                 coalesce(sum(out_demand.quantity),0) as planned
          from (%s) items
          -- Multiply with buckets
          cross join (
             select name as bucket, startdate, enddate
             from common_bucketdetail
             where bucket_id = '%s' and enddate > '%s' and startdate < '%s'
             ) d
          -- Include hierarchical children
          inner join item
          on item.lft between items.lft and items.rght
          -- Planned quantity
          left join out_demand
          on item.name = out_demand.item
          and d.startdate <= out_demand.plandate
          and d.enddate > out_demand.plandate
          and out_demand.plandate >= '%s'
          and out_demand.plandate < '%s'
          -- Grouping
          group by items.name, items.lft, items.rght, d.bucket, d.startdate, d.enddate
        ) x
        -- Requested quantity
        inner join item
        on item.lft between x.lft and x.rght
        left join demand
        on item.name = demand.item_id
        and x.startdate <= demand.due
        and x.enddate > demand.due
        and demand.due >= '%s'
        and demand.due < '%s'
        and demand.status = 'open'
        -- Grouping
        group by x.name, x.lft, x.rght, x.bucket, x.startdate, x.enddate
        ) y
        -- Ordering and grouping
        group by y.name, y.lft, y.rght, y.bucket, y.startdate, y.enddate
        order by %s, y.startdate
       ''' % (basesql, request.report_bucket, request.report_startdate,
              request.report_enddate, request.report_startdate,
              request.report_enddate, request.report_startdate,
              request.report_enddate, sortsql)
    cursor.execute(query, baseparams)

    # Build the python result
    previtem = None
    for row in cursor.fetchall():
      if row[0] != previtem:
        backlog = startbacklogdict.get(row[0], 0)
        previtem = row[0]
      backlog += float(row[4]) - float(row[5])
      yield {
        'item': row[0],
        'bucket': row[1],
        'startdate': python_date(row[2]),
        'enddate': python_date(row[3]),
        'demand': round(row[4], 1),
        'supply': round(row[5], 1),
        'backlog': round(backlog, 1)
        }


class DetailReport(GridReport):
  '''
  A list report to show delivery plans for demand.
  '''
  template = 'output/demandplan.html'
  title = _("Demand plan detail")
  model = Demand
  basequeryset = Demand.objects.all()
  permissions = (("view_demand_report", "Can view demand report"),)
  frozenColumns = 0
  editable = False
  multiselect = False
  rows = (
    GridFieldInteger('id', title=_('id'), key=True,editable=False, hidden=True),
    GridFieldText('demand', title=_('demand'), editable=False, formatter='detail', extra="role:'input/demand'"),
    GridFieldText('item', title=_('item'), editable=False, formatter='detail', extra="role:'input/item'"),
    GridFieldText('customer', title=_('customer'), editable=False, formatter='detail', extra="role:'input/customer'"),
    GridFieldNumber('quantity', title=_('quantity'), editable=False),
    GridFieldNumber('planquantity', title=_('planned quantity'), editable=False),
    GridFieldDateTime('due', title=_('due date'), editable=False),
    GridFieldDateTime('plandate', title=_('planned date'), editable=False),
    GridFieldInteger('operationplan', title=_('operationplan'), editable=False),
    )

  @classmethod
  def extra_context(reportclass, request, *args, **kwargs):
    if args and args[0]:
      request.session['lasttab'] = 'plandetail'
    return {'active_tab': 'plandetail'}


@staff_member_required
def OperationPlans(request):
  # Check permissions
  if request.method != "GET" or not request.is_ajax(): 
    return HttpResponseBadRequest('Only ajax get requests allowed')  
  if not request.user.has_perm("view_demand_report"):
    return HttpResponseForbidden('<h1>%s</h1>' % _('Permission denied'))
  
  # Collect list of selected sales orders
  so_list = request.GET.getlist('demand')
  
  # Find proposed associated with this sales order
  result = []
  id_list = [
    peg.operationplan
    for peg in DemandPegging.objects.all().using(request.database).filter(demand__in=so_list)
    ]
  for o in PurchaseOrder.objects.all().using(request.database).filter(id__in=id_list, status='proposed'):
    result.append({
      'id': o.id,
      'type': "PO",
      'item': o.item.name,
      'location': o.location.name,    
      'origin': o.supplier.name,
      'startdate': str(o.startdate.date()),
      'enddate': str(o.enddate.date()),
      'quantity': float(o.quantity),
      'value': float(o.quantity * o.item.price),
      'criticality': float(o.criticality)
    })
  for o in DistributionOrder.objects.all().using(request.database).filter(id__in=id_list, status='proposed'):
    result.append({
      'id': o.id,
      'type': "DO",
      'item': o.item.name,
      'location': o.location.name,    
      'origin': o.origin.name,
      'startdate': str(o.startdate),
      'enddate': str(o.enddate),
      'quantity': float(o.quantity),
      'value': float(o.quantity * o.item.price),
      'criticality': float(o.criticality)
    })
  for o in OperationPlan.objects.all().using(request.database).filter(id__in=id_list, status='proposed'):
    result.append({
      'id': o.id,
      'type': "MO",
      'item': '',
      'location': o.operation.location.name,    
      'origin': o.operation.name,
      'startdate': str(o.startdate.date()),
      'enddate': str(o.enddate.date()),
      'quantity': float(o.quantity),
      'value': '',
      'criticality': float(o.criticality)
    })
  
  return HttpResponse(
    content=json.dumps(result),
    content_type='application/json; charset=%s' % settings.DEFAULT_CHARSET
    )
  