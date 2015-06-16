/***************************************************************************
 *                                                                         *
 * Copyright (C) 2007-2015 by Johan De Taeye, frePPLe bvba                 *
 *                                                                         *
 * This library is free software; you can redistribute it and/or modify it *
 * under the terms of the GNU Affero General Public License as published   *
 * by the Free Software Foundation; either version 3 of the License, or    *
 * (at your option) any later version.                                     *
 *                                                                         *
 * This library is distributed in the hope that it will be useful,         *
 * but WITHOUT ANY WARRANTY; without even the implied warranty of          *
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the            *
 * GNU Affero General Public License for more details.                     *
 *                                                                         *
 * You should have received a copy of the GNU Affero General Public        *
 * License along with this program.                                        *
 * If not, see <http://www.gnu.org/licenses/>.                             *
 *                                                                         *
 ***************************************************************************/

#define FREPPLE_CORE
#include "frepple/model.h"

namespace frepple
{


DECLARE_EXPORT Plan* Plan::thePlan;
DECLARE_EXPORT const MetaCategory* Plan::metadata;


int Plan::initialize()
{
  // Initialize the plan metadata.
  metadata = MetaCategory::registerCategory<Plan>("plan","");
  registerFields(const_cast<MetaCategory*>(metadata));

  // Initialize the Python type
  PythonType& x = PythonExtension<Plan>::getPythonType();
  x.setName("parameters");
  x.setDoc("frePPLe global settings");
  x.supportgetattro();
  x.supportsetattro();
  int tmp = x.typeReady();
  const_cast<MetaCategory*>(metadata)->pythonClass = x.type_object();

  // Create a singleton plan object
  // Since we can count on the initialization being executed only once, also
  // in a multi-threaded configuration, we don't need a more advanced mechanism
  // to protect the singleton plan.
  thePlan = new Plan();

  // Add access to the information with a global attribute.
  PythonInterpreter::registerGlobalObject("settings", &Plan::instance());
  return tmp;
}


DECLARE_EXPORT Plan::~Plan()
{
  // Closing the logfile
  Environment::setLogFile("");

  // Clear the pointer to this singleton object
  thePlan = NULL;
}


DECLARE_EXPORT void Plan::setCurrent (Date l)
{
  // Update the time
  cur_Date = l;

  // Let all operationplans check for new ProblemBeforeCurrent and
  // ProblemBeforeFence problems.
  for (Operation::iterator i = Operation::begin(); i != Operation::end(); ++i)
    i->setChanged();
}


DECLARE_EXPORT void Plan::writeElement(Serializer *o, const Keyword& tag, mode m) const
{
  const MetaClass& meta = getType();

  // Write the head
  if (m != NOHEAD && m != NOHEADTAIL)
  {
    if (meta.isDefault)
      o->BeginObject(tag);
    else
      o->BeginObject(tag, Tags::type, getType().type);
  }

  // Write my own fields
  if (meta.category)
    for (MetaClass::fieldlist::const_iterator i = meta.category->getFields().begin(); i != meta.category->getFields().end(); ++i)
      (*i)->writeField(*o);
  for (MetaClass::fieldlist::const_iterator i = meta.getFields().begin(); i != meta.getFields().end(); ++i)
    (*i)->writeField(*o);
  PythonDictionary::write(o, getDict());

  // Write all categories
  MetaCategory::persist(o);

  // Write the tail
  if (m != NOHEADTAIL && m != NOTAIL)
    o->EndObject(tag);
}

}
